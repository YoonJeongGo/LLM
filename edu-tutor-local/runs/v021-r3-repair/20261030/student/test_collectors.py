"""Collector-only CPU tests: temporary fixtures and read-only historical records."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import contextmanager

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[3]
sys.path.insert(0,str(ROOT/'src'))
import collect_journeys as collector
from latency_breakdown import breakdown


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')


@contextmanager
def fixture_directory():
    parent=(BASE/'collector-fixtures').resolve()
    parent.mkdir(exist_ok=True)
    folder=Path(tempfile.mkdtemp(prefix='cpu-',dir=parent)).resolve()
    assert folder.is_relative_to(parent)
    yield folder  # Preserve tiny synthetic fixtures as test evidence; no recursive cleanup.


class CollectorsTest(unittest.TestCase):
    def fixture(self,root,*,controlled=False):
        base=root/'runs/new-cohort/student';source=base/'frozen'
        specs={'provenance':{'purpose':'test independent 2+2' if not controlled else 'test historical short control','planned_question_events':4 if not controlled else 10},
               'journeys':[{'id':name,'kind':'concept','question':'CPU collector fixture',**({'followup':{'question':'CPU followup'}} if not controlled else {})}
                           for name in (['N01','N02'] if not controlled else ['J01','J02'])]}
        write(source/'journeys.json',specs)
        frozen={'input_sha256':collector.digest(source/'journeys.json'),'source_hashes':{},'stop_after_first_voice':controlled}
        write(source/'execution-version.json',frozen)
        write(root/'runs/phase2/current/resource-budget.json',{'requests':[]})
        (root/'.local').mkdir()
        with sqlite3.connect(root/'.local/tutor.sqlite3') as db:
            db.execute('CREATE TABLE messages(id TEXT PRIMARY KEY,payload TEXT)')
            db.execute('CREATE TABLE lessons(id TEXT PRIMARY KEY,payload TEXT)')
        return base,source,specs,frozen

    def test_new_cohort_uses_file_relative_base_and_frozen_inputs(self):
        with fixture_directory() as tmp:
            root=Path(tmp);base,source,specs,_=self.fixture(root)
            write(base/'journeys.json',{'journeys':[{'id':'WRONG_MUTABLE_INPUT'}]})
            before=collector.digest(source/'journeys.json')
            with patch.object(collector,'__file__',str(base/'collect_journeys.py')):
                report=collector.collect(root,'frozen')
            summary=collector.read(report/'summary.json')
            self.assertEqual([c['id'] for c in summary['cases']],['N01','N02'])
            self.assertEqual(summary['latency_denominator'],4)
            self.assertEqual(summary['measurement_mode'],'FULL_STUDENT_JOURNEY')
            self.assertTrue(str(report).startswith(str(source)))
            self.assertEqual(collector.digest(source/'journeys.json'),before)

    def test_short_attempts_export_separate_records_and_gallery(self):
        with fixture_directory() as tmp:
            root=Path(tmp);base,source,_,_=self.fixture(root,controlled=True)
            for attempt in ('cold','warm'):
                write(source/('J01-'+attempt)/'actual.json',{'id':'J01','attempt':attempt,'version':'frozen','source_hashes':{},
                    'source_unchanged_at_end':True,'status':'FAILED_NO_RETRY','completed_at':'2026-10-30T00:00:01Z',
                    'measurement_mode':'SHORT_CONTROLLED_FIRST_VOICE_ONLY_NOT_FULL_STUDENT_JOURNEY',
                    'events':[],'responses':[],'owned_jobs':[],'failure':'CPU fixture has no audio'})
            with patch.object(collector,'__file__',str(base/'collect_journeys.py')):
                report=collector.collect(root,'frozen')
            summary=collector.read(report/'summary.json')
            self.assertEqual([c['id'] for c in summary['cases']],['J01-cold','J01-warm'])
            self.assertEqual(summary['latency_denominator'],2)
            for name in ('cold','warm'):
                record=collector.read(report/('J01-'+name+'.json'))
                self.assertEqual(record['question_id'],'J01')
                self.assertEqual(record['attempt'],name)
                self.assertIsNone(record['evidence_requirements']['all_steps_naturally_ended'])
                self.assertEqual(record['status'],'FAILED_NO_RETRY')
            gallery=(report/'gallery.html').read_text(encoding='utf-8')
            self.assertIn('J01-cold.json',gallery);self.assertIn('J01-warm.json',gallery)
            self.assertIn('SHORT_CONTROLLED_FIRST_VOICE_ONLY',gallery)
            self.assertNotIn('새 독립 28문항',gallery)

    def test_discovery_retains_unrun_warm_and_supports_explicit_subset(self):
        with fixture_directory() as tmp:
            source=Path(tmp);write(source/'J01-cold/actual.json',{})
            specs={'journeys':[{'id':'J01'},{'id':'J02'}]}
            rows=collector.execution_entries(source,specs,controlled=True)
            self.assertEqual([r['case_id'] for r in rows],['J01-cold','J01-warm'])
            self.assertFalse(rows[1]['path'].exists())
            self.assertEqual(collector.execution_entries(source,specs,controlled=True,attempt='cold')[0]['case_id'],'J01-cold')
            with self.assertRaises(ValueError):collector.execution_entries(source,specs,attempt='warm')

    def test_new_cohort_gallery_has_both_questions(self):
        with fixture_directory() as tmp:
            root=Path(tmp);cases=[{'id':ident,'status':'FAILED_NO_RETRY','spec':{'question':'CPU fixture'},'answers':[],
                    'playback':[],'lessons':[],'timings':{},'screenshots':[]} for ident in ('N01','N02')]
            collector.write_gallery(root,cases,{},provenance={'planned_question_events':4,'purpose':'Independent frozen questions'})
            text=(root/'gallery.html').read_text(encoding='utf-8')
            self.assertIn('<h2>N01:',text);self.assertIn('<h2>N02:',text)
            self.assertIn('Independent frozen questions',text)

    def test_storage_transport_clocks_link_owned_job_without_fake_valid_latency(self):
        storage={'clock':'host_perf_counter','phases':{'db_commit':{'seconds':.25,'count':2}},'intervals_not_all_additive':True}
        transport={'clock':'parent_perf_counter','first_delta_consumer_elapsed_seconds':.1,'queue_wait_seconds_total':.5}
        record={'owned_jobs':[{'id':'own','kind':'chat','request_id':'q','state':'succeeded','result':{'message_id':'m'},'storage_timing':storage},
            {'id':'old-failed','kind':'chat','state':'cancelled'}, {'id':'speech','kind':'speech','state':'succeeded','storage_timing':{'wrong':'exclude'}}]}
        messages=[{'id':'m','role':'assistant','request_id':'q','generation_snapshot':{'transport_timing':transport},'latency':{'request_to_verified_core_seconds':2}}]
        result=breakdown(record,messages,{},[],{'question_to_first_valid_explanation':[{'request_id':'q','first_valid_explanation_ms':None}]})
        self.assertEqual(result['answers'][0]['transport_timing'],transport)
        self.assertEqual(result['answers'][0]['owned_chat_job_ids'],['own'])
        self.assertEqual(result['owned_chat_storage'][0]['storage_timing'],storage)
        self.assertEqual(len(result['owned_chat_storage']),2)
        self.assertEqual(result['owned_chat_storage'][1]['storage_timing'],{'status':'NOT_MEASURED'})
        self.assertIsNone(result['unattributed_boundary_differences'][0]['question_to_first_valid_seconds'])
        self.assertIn('unverified',result['measurement_boundaries']['first_delta'])

    def test_existing_actual_read_only_missing_new_measurements_stay_missing(self):
        review=collector.read(ROOT/'runs/v021-support/20261029/student/final-v021-r3-combined/J02.json')
        path=Path(review['actual_json']);before=hashlib.sha256(path.read_bytes()).hexdigest()
        record=collector.read(path)
        result=breakdown(record,record.get('actual_messages',[]),{},[],{})
        self.assertTrue(result['answers'])
        for answer in result['answers']:self.assertEqual(answer['transport_timing'],{'status':'NOT_MEASURED'})
        self.assertEqual(before,hashlib.sha256(path.read_bytes()).hexdigest())

    def test_repeat_partition_never_increases_primary_denominator(self):
        spec={'id':'N01','kind':'write_sql','question':'initial','followup':{'question':'same followup'}}
        rows=[{'input_kind':'text','question_text':'initial','first_valid_explanation_ms':1000},
              {'input_kind':'followup','question_text':'same followup','first_valid_explanation_ms':2000},
              {'input_kind':'followup','question_text':'same followup','first_valid_explanation_ms':3000}]
        primary,repeated=collector.partition_questions(rows,spec,primary_count=2,repeat_expected=True)
        self.assertEqual(len(primary),2);self.assertEqual(len(repeated),1)
        self.assertFalse(repeated[0]['included_in_primary_accuracy_denominator'])
        self.assertEqual(collector.measured_stats(row['first_valid_explanation_ms'] for row in primary)['max_ms'],2000)
        self.assertEqual(collector.measured_stats(row['first_valid_explanation_ms'] for row in repeated)['max_ms'],3000)
        primary,missing=collector.partition_questions(rows[:1],spec,primary_count=2,repeat_expected=True,reason='first failure')
        self.assertEqual(primary[1]['status'],'NOT_REACHED');self.assertEqual(missing[0]['status'],'NOT_REACHED')
        with self.assertRaises(ValueError):collector.partition_questions(rows,spec,primary_count=2,repeat_expected=False)
        with self.assertRaises(ValueError):collector.partition_questions(rows+rows[-1:],spec,primary_count=2,repeat_expected=True)
        rows[-1]['question_text']='changed'
        with self.assertRaises(ValueError):collector.partition_questions(rows,spec,primary_count=2,repeat_expected=True)

    def test_missing_repeat_keeps_separate_planned_denominator(self):
        with fixture_directory() as tmp:
            root=Path(tmp);base,source,_,frozen=self.fixture(root)
            frozen['repeat_followup_case_id']='N01';write(source/'execution-version.json',frozen)
            with patch.object(collector,'__file__',str(base/'collect_journeys.py')):
                report=collector.collect(root,'frozen')
            summary=collector.read(report/'summary.json')
            self.assertEqual(summary['latency_denominator'],4)
            self.assertEqual(summary['repeat_stability']['planned_question_denominator'],1)
            self.assertEqual(summary['repeat_stability']['question_events'][0]['status'],'NOT_RUN')

    def test_collect_three_submissions_splits_repeat_and_preserves_failed_record(self):
        with fixture_directory() as tmp:
            root=Path(tmp);base,source,specs,frozen=self.fixture(root)
            frozen['repeat_followup_case_id']='N01'
            frozen['expected_question_plan']={'N01':[{'kind':'initial'},{'kind':'followup'},{'kind':'repeat_followup'}]}
            write(source/'execution-version.json',frozen)
            actual=source/'N01/actual.json'
            write(actual,{'id':'N01','attempt':None,'version':'frozen','source_hashes':{},'source_unchanged_at_end':True,
                'status':'FAILED_NO_RETRY','completed_at':'2026-10-30T00:00:01Z','repeat_followup':True,
                'question_plan':frozen['expected_question_plan']['N01'],'events':[],'responses':[],'owned_jobs':[],
                'followup_cycles':[{'cohort':'primary','status':'COMPLETED_AND_RESTORED'},
                    {'cohort':'repeat_stability_only','status':'PREPARING'}],'failure':'CPU fixture repeat failed'})
            before=collector.digest(actual)
            timing={'question_to_first_valid_explanation':[
                {'input_kind':'text','question_text':'CPU collector fixture','first_valid_explanation_ms':100},
                {'input_kind':'followup','question_text':'CPU followup','first_valid_explanation_ms':200},
                {'input_kind':'followup','question_text':'CPU followup','first_valid_explanation_ms':None}],
                'interruptions':[{'old_audio_stopped_ms':10,'supplement_started_ms':200},
                    {'old_audio_stopped_ms':20,'supplement_started_ms':None}]}
            with patch.object(collector,'__file__',str(base/'collect_journeys.py')),patch.object(collector,'bound_latencies',return_value=timing):
                report=collector.collect(root,'frozen')
            summary=collector.read(report/'summary.json');case=collector.read(report/'N01.json')
            self.assertEqual(summary['latency_denominator'],4)
            self.assertEqual(len(summary['question_events']),4)
            self.assertEqual(summary['question_to_audio']['measured_count'],2)
            self.assertEqual(summary['interrupt_to_native_pause']['max_ms'],10)
            self.assertEqual(summary['repeat_stability']['planned_question_denominator'],1)
            self.assertEqual(summary['repeat_stability']['interrupt_to_native_pause']['max_ms'],20)
            self.assertEqual(case['status'],'FAILED_NO_RETRY')
            self.assertEqual(case['repeat_stability']['cycles'][0]['status'],'PREPARING')
            self.assertEqual(collector.digest(actual),before)


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(CollectorsTest)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    write(BASE/'collector-repeat-cpu-preflight.json',{'status':'PASS' if result.wasSuccessful() else 'FAIL','tests':result.testsRun,
        'failures':len(result.failures),'errors':len(result.errors),'actual_model_TTS_OCR_calls':0,
        'scope':'Temporary collector fixtures plus read-only original J02 actual record; no original file copying or mutation'})
    raise SystemExit(0 if result.wasSuccessful() else 1)
