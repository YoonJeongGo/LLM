import importlib.util
from pathlib import Path
import pytest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))

spec=importlib.util.spec_from_file_location('proposed_glyph_collector',Path(__file__).resolve().parents[1]/'scripts/finish_collect_journeys.py')
collector=importlib.util.module_from_spec(spec);spec.loader.exec_module(collector)

def fixture():
    step={'gesture':{'kind':'write','target_element_id':'eq'},'board_actions':[{'type':'equation','element_id':'eq','latex':'1+2=3'}]}
    event={'elements':[{'id':'eq','equation_html':'<span class="katex">fixture</span>',
        'rect':{'x':0,'y':0,'width':1000,'height':50},
        'equation_glyph_rects':[{'x':10,'y':10,'width':10,'height':20},{'x':80,'y':10,'width':10,'height':20}]}],
        'cells':[],'pointer_end':{'x':15,'y':20}}
    return event,step

@pytest.mark.parametrize('x',[6,15,80,94])
def test_any_glyph_is_valid_not_only_the_last_anchor(x):
    event,step=fixture();event['pointer_end']['x']=x
    assert collector.pointer_binding(event,step)['status']=='PASS'

@pytest.mark.parametrize('x',[5,40,95,986])
def test_blank_wrapper_and_between_glyphs_are_not_valid(x):
    event,step=fixture();event['pointer_end']['x']=x
    assert collector.pointer_binding(event,step)['status']=='FAIL'

@pytest.mark.parametrize('missing',[None,[]])
def test_old_or_empty_glyph_measurement_cannot_pass(missing):
    event,step=fixture();event['elements'][0]['equation_glyph_rects']=missing
    assert collector.pointer_binding(event,step)['status']=='NOT_MEASURED'

def test_actual_equation_from_a_previous_step_still_requires_glyphs():
    event,step=fixture();step['board_actions']=[];event['pointer_end']['x']=986
    assert collector.pointer_binding(event,step)['status']=='FAIL'

@pytest.mark.parametrize('glyph',[{},None,{'x':0,'y':0,'width':float('inf'),'height':30},{'x':0,'y':0,'width':0,'height':30}])
def test_malformed_or_empty_glyph_is_not_a_pass(glyph):
    event,step=fixture();event['elements'][0]['equation_glyph_rects']=[glyph]
    assert collector.pointer_binding(event,step)['status']=='FAIL'

def test_selected_source_cell_remains_separate_from_equation_geometry():
    event,step=fixture();event['cells']=[{'id':'source-row-zero','selected':True,'rect':{'x':980,'y':0,'width':20,'height':30}}]
    event['pointer_end']['x']=986
    assert collector.pointer_binding(event,step)['status']=='PASS'
