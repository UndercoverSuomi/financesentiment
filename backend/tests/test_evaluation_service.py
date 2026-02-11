from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings
from app.services.evaluation_service import EvaluationService


def test_evaluation_service_computes_metrics(tmp_path: Path) -> None:
    dataset = tmp_path / 'gold.csv'
    dataset.write_text(
        '\n'.join(
            [
                'target_type,ticker,gold_label,text,title,selftext,parent_text',
                'comment,AAPL,BULLISH,"buy aapl now",AAPL thread,,',
                'comment,AAPL,BEARISH,"short aapl now",AAPL thread,,',
                'comment,TSLA,UNCLEAR,"idk",TSLA thread,,',
            ]
        ),
        encoding='utf-8',
    )

    settings = get_settings().model_copy(update={'evaluation_default_max_rows': 100})
    service = EvaluationService(settings=settings)
    report = service.evaluate(dataset_path=str(dataset), max_rows=100)

    assert report['rows_evaluated'] == 3
    assert 0.0 <= report['accuracy'] <= 1.0
    assert 0.0 <= report['macro_f1'] <= 1.0
    assert 0.0 <= report['weighted_f1'] <= 1.0
    assert 0.0 <= report['expected_calibration_error'] <= 1.0
    assert len(report['per_label']) == 4
    assert len(report['confusion']) == 16
