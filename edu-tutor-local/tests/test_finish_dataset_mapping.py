from pathlib import Path

import yaml

from edu_tutor.api.admin import EDUCATION_DATASETS


def test_education_ids_map_to_exact_existing_config_and_development_files():
    root=Path(__file__).resolve().parents[1]
    assert set(EDUCATION_DATASETS)=={'finish-v2','finish-v2-diverse-v2','finish-v2-reason-v3'}
    for config,paths in EDUCATION_DATASETS.values():
        actual=yaml.safe_load((root/config).read_text(encoding='utf-8'))
        assert list(paths)==actual['training']['dataset_paths']
        assert len(paths)==2 and all((root/path).is_file() for path in paths)
        assert all('/final/' not in path and not path.endswith('/test.jsonl') for path in paths)
        assert actual['training']['max_epochs']==3 and actual['training']['auto_promote_adapter'] is False
    assert EDUCATION_DATASETS['finish-v2'][1][0]=='runs/finish-v2/20261028/education/development/train.jsonl'
    assert EDUCATION_DATASETS['finish-v2'][1][1]==EDUCATION_DATASETS['finish-v2-diverse-v2'][1][1]
