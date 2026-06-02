# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

from collections import defaultdict
from enum import Enum
from typing import Dict, List

import numpy as np
import pandas as pd
from logger import ERROR, WARNING, logger
from pydantic import BaseModel, ConfigDict

EXCEL_WEIGHTS_MATRIX_PATH = "weights_concept_matrix.xlsx"


def create_weights_df(path=EXCEL_WEIGHTS_MATRIX_PATH):
    try:
        df = pd.read_excel(
            path, header=0, index_col=0, sheet_name=1
        )  # second sheet, proper copy of the first one
        if df.isnull().values.any():
            logger().logp(
                WARNING,
                f"The weights matrix contains NaN values. Please check the file at {path}. Missing weights will be considered as 0.",
            )
            df = df.fillna(0)
        return df
    except FileNotFoundError as e:
        logger().logp(
            ERROR,
            f"Weights matrix file not found at {path}. Please ensure the file exists. Error: {e}",
        )
        return pd.DataFrame()
    except Exception as e:
        logger().logp(ERROR, f"An error occurred while reading the weights matrix: {e}")
        return pd.DataFrame()


def create_enum_from_df_columns(df) -> Enum:
    try:
        return Enum(
            "keywords", {s: s.replace(" ", "_").lower() for s in df.index.tolist()}
        )
    except Exception as e:
        logger().logp(
            ERROR,
            f"An error occurred while creating the enum from DataFrame columns: {e}",
        )
        return Enum("keywords", {"OTHER": "other"})


_weights_df = create_weights_df()

KeywordsEnum = create_enum_from_df_columns(_weights_df)


class LLMResponseClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    keyword: KeywordsEnum
    confidence: float


class ListLLMResponseClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: List[LLMResponseClassification]

def compute_mark_scores(
    keyword_score_dicts: List[LLMResponseClassification],
    df: pd.DataFrame = _weights_df,
    agg: str = "sum",
    with_best_stats: bool = False,
):
    if not keyword_score_dicts:
        return ({}, [], {}) if with_best_stats else {}

    collected = defaultdict(list)

    for d in keyword_score_dicts:
        keyword = d.keyword.name
        score = d.confidence
        if keyword not in df.index:
            continue
        active_marks = df.columns[df.loc[keyword] == 1]
        for m in active_marks:
            collected[m].append(score)

    if not collected:
        return ({}, [], {}) if with_best_stats else {}

    if isinstance(agg, str):
        if agg == "max":
            reducer = max
        elif agg == "sum":
            reducer = sum
        elif agg == "mean":
            reducer = lambda lst: sum(lst) / len(lst)
        else:
            raise ValueError("Unknown aggregation method")
    else:
        raise ValueError("Invalid aggregation parameter")

    scores = {mark: reducer(scores) for mark, scores in collected.items()}

    if not with_best_stats:
        return scores

    # Find best marks and their keyword counts
    if not scores:
        return {}, [], {}
    best_value = max(scores.values())
    best_marks = [m for m, v in scores.items() if v == best_value]
    counts = {m: len(collected[m]) for m in best_marks}
    count_min = min(
        counts.values()
    )  # We take the minimum count that led to the higher confidence score
    return scores, best_marks, count_min


def normalize_scores(mark_scores: Dict[str, float]) -> Dict[str, float]:
    """
    Normalize scores to be between 1 and 10.
    """
    if not mark_scores:
        return {}

    min_score = min(mark_scores.values())
    max_score = max(mark_scores.values())

    if min_score == max_score:
        return {mark: 1.0 for mark in mark_scores}

    normalized = {}
    for mark, score in mark_scores.items():
        score_range = [1, 10]
        normalized[mark] = int(
            np.round(
                (1 - (score - min_score) / (max_score - min_score))
                * (score_range[1] - score_range[0])
                + score_range[0]
            )
        )
    return normalized


def compute_adaptative_threshold(score: float, min_score=0.5, nb_attr_normalization=1):
    MIN_SCORE_TOLERATED = min_score
    TARGET_THRESHOLD_WITH_MAX_SCORE = 10  # if the LLM confidence score is 1, we want to keep mark with (max score - 10%)
    if score < MIN_SCORE_TOLERATED:
        return 0
    else:
        threshold = (
            TARGET_THRESHOLD_WITH_MAX_SCORE
            * (
                (score - MIN_SCORE_TOLERATED)
                / (1 * nb_attr_normalization - MIN_SCORE_TOLERATED)
            )
            ** 2
        )  # nb_attr_normalization is here to avoid too high threshold when multiple attributes are used
        return score * (
            1 - threshold / 100
        )  # score is between 0 and 1 so we need to convert threshold to a fraction
