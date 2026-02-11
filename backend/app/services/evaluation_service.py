from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings
from app.schemas.common import StanceLabel, TargetType
from app.services.stance_service import StanceService
from app.services.ticker_extractor import TickerExtractor


LABEL_ORDER = [
    StanceLabel.bullish.value,
    StanceLabel.bearish.value,
    StanceLabel.neutral.value,
    StanceLabel.unclear.value,
]


@dataclass(slots=True)
class GoldLabelRow:
    row_id: int
    target_type: TargetType
    ticker: str
    gold_label: str
    text: str
    title: str
    selftext: str
    parent_text: str


class EvaluationService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._ticker_extractor = TickerExtractor(settings)
        self._stance_service = StanceService(settings, self._ticker_extractor)

    def evaluate(self, dataset_path: str | None = None, max_rows: int | None = None) -> dict:
        path = self._resolve_dataset_path(dataset_path)
        limit = max_rows if max_rows is not None else self._settings.evaluation_default_max_rows
        rows = self._load_rows(path=path, max_rows=max(limit, 1))

        confusion = {(actual, predicted): 0 for actual in LABEL_ORDER for predicted in LABEL_ORDER}
        model_version_counts: dict[str, int] = {}
        total = 0
        correct = 0
        direct_detection = 0
        context_inference = 0
        missing_prediction = 0
        bin_count = [0] * 10
        bin_conf_sum = [0.0] * 10
        bin_correct_sum = [0.0] * 10
        error_examples: list[dict] = []

        for row in rows:
            total += 1
            predicted, confidence, source, model_version = self._predict_row(row)
            confusion[(row.gold_label, predicted)] += 1
            model_version_counts[model_version] = model_version_counts.get(model_version, 0) + 1

            is_correct = predicted == row.gold_label
            if is_correct:
                correct += 1
            else:
                if len(error_examples) < 25:
                    error_examples.append(
                        {
                            'row_id': row.row_id,
                            'ticker': row.ticker,
                            'actual': row.gold_label,
                            'predicted': predicted,
                            'confidence': confidence,
                            'source': source,
                            'text': row.text[:280],
                        }
                    )

            if source in {'cashtag', 'token', 'synonym'}:
                direct_detection += 1
            elif source == 'context':
                context_inference += 1
            else:
                missing_prediction += 1

            bin_idx = min(max(int(confidence * 10), 0), 9)
            bin_count[bin_idx] += 1
            bin_conf_sum[bin_idx] += confidence
            bin_correct_sum[bin_idx] += 1.0 if is_correct else 0.0

        per_label: list[dict] = []
        macro_f1_sum = 0.0
        weighted_f1_sum = 0.0
        for label in LABEL_ORDER:
            tp = confusion[(label, label)]
            fp = sum(confusion[(actual, label)] for actual in LABEL_ORDER if actual != label)
            fn = sum(confusion[(label, predicted)] for predicted in LABEL_ORDER if predicted != label)
            support = sum(confusion[(label, predicted)] for predicted in LABEL_ORDER)
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
            macro_f1_sum += f1
            weighted_f1_sum += f1 * support
            per_label.append(
                {
                    'label': label,
                    'support': support,
                    'precision': precision,
                    'recall': recall,
                    'f1': f1,
                    'tp': tp,
                    'fp': fp,
                    'fn': fn,
                }
            )

        ece = 0.0
        if total > 0:
            for idx in range(10):
                if bin_count[idx] == 0:
                    continue
                avg_conf = bin_conf_sum[idx] / bin_count[idx]
                avg_acc = bin_correct_sum[idx] / bin_count[idx]
                ece += (bin_count[idx] / total) * abs(avg_acc - avg_conf)

        confusion_rows = [
            {
                'actual': actual,
                'predicted': predicted,
                'count': count,
            }
            for (actual, predicted), count in confusion.items()
        ]
        confusion_rows.sort(key=lambda row: (LABEL_ORDER.index(row['actual']), LABEL_ORDER.index(row['predicted'])))

        model_versions = [
            {'model_version': model_version, 'count': count}
            for model_version, count in sorted(model_version_counts.items(), key=lambda item: item[1], reverse=True)
        ]

        return {
            'dataset_path': str(path),
            'rows_evaluated': total,
            'accuracy': (correct / total) if total > 0 else 0.0,
            'macro_f1': (macro_f1_sum / len(LABEL_ORDER)) if LABEL_ORDER else 0.0,
            'weighted_f1': (weighted_f1_sum / total) if total > 0 else 0.0,
            'expected_calibration_error': ece,
            'direct_detection_rate': (direct_detection / total) if total > 0 else 0.0,
            'context_inference_rate': (context_inference / total) if total > 0 else 0.0,
            'missing_prediction_rate': (missing_prediction / total) if total > 0 else 0.0,
            'model_versions': model_versions,
            'per_label': per_label,
            'confusion': confusion_rows,
            'error_examples': error_examples,
        }

    def _predict_row(self, row: GoldLabelRow) -> tuple[str, float, str, str]:
        predictions = self._stance_service.analyze_target(
            target_type=row.target_type,
            text=row.text,
            title=row.title,
            selftext=row.selftext,
            parent_text=row.parent_text,
        )
        for prediction in predictions:
            if prediction.mention.ticker != row.ticker:
                continue
            return (
                prediction.label.value,
                max(min(float(prediction.confidence), 1.0), 0.0),
                prediction.mention.source,
                prediction.model_version,
            )
        return (StanceLabel.unclear.value, 0.0, 'missing', 'none')

    def _load_rows(self, path: Path, max_rows: int) -> list[GoldLabelRow]:
        rows: list[GoldLabelRow] = []
        with path.open('r', encoding='utf-8', newline='') as file:
            reader = csv.DictReader(file)
            required = {'target_type', 'ticker', 'gold_label', 'text'}
            missing = required.difference({field or '' for field in (reader.fieldnames or [])})
            if missing:
                raise ValueError(f'gold label csv is missing required columns: {sorted(missing)}')

            for idx, raw in enumerate(reader, start=1):
                if len(rows) >= max_rows:
                    break
                target_type_str = str(raw.get('target_type', '')).strip().lower()
                if target_type_str not in {'submission', 'comment'}:
                    raise ValueError(f'invalid target_type at row {idx}: {target_type_str}')
                ticker = str(raw.get('ticker', '')).strip().upper()
                if not ticker:
                    raise ValueError(f'missing ticker at row {idx}')
                gold_label = str(raw.get('gold_label', '')).strip().upper()
                if gold_label not in LABEL_ORDER:
                    raise ValueError(f'invalid gold_label at row {idx}: {gold_label}')
                rows.append(
                    GoldLabelRow(
                        row_id=idx,
                        target_type=TargetType(target_type_str),
                        ticker=ticker,
                        gold_label=gold_label,
                        text=str(raw.get('text', '') or ''),
                        title=str(raw.get('title', '') or ''),
                        selftext=str(raw.get('selftext', '') or ''),
                        parent_text=str(raw.get('parent_text', '') or ''),
                    )
                )
        return rows

    def _resolve_dataset_path(self, dataset_path: str | None) -> Path:
        raw = dataset_path or str(self._settings.evaluation_dataset_file)
        path = Path(raw)
        if not path.is_absolute():
            path = (self._settings.repo_root / path).resolve()
        else:
            path = path.resolve()
        if not path.exists():
            raise FileNotFoundError(f'evaluation dataset not found: {path}')
        if path.suffix.lower() != '.csv':
            raise ValueError(f'evaluation dataset must be a .csv file: {path}')
        return path
