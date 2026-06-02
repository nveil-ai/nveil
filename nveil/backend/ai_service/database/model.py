# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

from shared.secrets import get_secret
from sqlalchemy import Column, DateTime, Float, Integer, String
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

_SCHEMA = get_secret("STATE_DATABASE_SCHEMA", "state_schema")


class UserProperties(Base):
    __tablename__ = "user_properties"
    __table_args__ = {"schema": _SCHEMA}

    user_id = Column(String, primary_key=True)
    tone = Column(String)
    compl_info = Column(String)


class TurnMetricsRecord(Base):
    """One row per conversation turn — stores per-step LLM metrics."""

    __tablename__ = "turn_metrics"
    __table_args__ = {"schema": _SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    room_id = Column(String, index=True)
    owner_id = Column(String)
    user_id = Column(String)
    source = Column(String, default="web")  # "web" or "sdk"

    # ── Entry classification (1 call) ──────────────────────────────
    entry_classif_elapsed_s = Column(Float)
    entry_classif_input_tokens = Column(Integer)
    entry_classif_cached_tokens = Column(Integer)
    entry_classif_output_tokens = Column(Integer)
    entry_classif_thinking_tokens = Column(Integer)

    # ── Planning transformation — up to 3 attempts ─────────────────
    planning_retries = Column(Integer, default=0)

    planning_1st_elapsed_s = Column(Float)
    planning_1st_input_tokens = Column(Integer)
    planning_1st_cached_tokens = Column(Integer)
    planning_1st_output_tokens = Column(Integer)
    planning_1st_thinking_tokens = Column(Integer)

    planning_2nd_elapsed_s = Column(Float)
    planning_2nd_input_tokens = Column(Integer)
    planning_2nd_cached_tokens = Column(Integer)
    planning_2nd_output_tokens = Column(Integer)
    planning_2nd_thinking_tokens = Column(Integer)

    planning_3rd_elapsed_s = Column(Float)
    planning_3rd_input_tokens = Column(Integer)
    planning_3rd_cached_tokens = Column(Integer)
    planning_3rd_output_tokens = Column(Integer)
    planning_3rd_thinking_tokens = Column(Integer)

    # ── XML generation — up to 3 attempts (graph-level retry) ──────
    xml_gen_retries = Column(Integer, default=0)

    xml_gen_1st_elapsed_s = Column(Float)
    xml_gen_1st_input_tokens = Column(Integer)
    xml_gen_1st_cached_tokens = Column(Integer)
    xml_gen_1st_output_tokens = Column(Integer)
    xml_gen_1st_thinking_tokens = Column(Integer)

    xml_gen_2nd_elapsed_s = Column(Float)
    xml_gen_2nd_input_tokens = Column(Integer)
    xml_gen_2nd_cached_tokens = Column(Integer)
    xml_gen_2nd_output_tokens = Column(Integer)
    xml_gen_2nd_thinking_tokens = Column(Integer)

    xml_gen_3rd_elapsed_s = Column(Float)
    xml_gen_3rd_input_tokens = Column(Integer)
    xml_gen_3rd_cached_tokens = Column(Integer)
    xml_gen_3rd_output_tokens = Column(Integer)
    xml_gen_3rd_thinking_tokens = Column(Integer)

    # ── Keyword classification (1 call) ────────────────────────────
    keyword_classif_elapsed_s = Column(Float)
    keyword_classif_input_tokens = Column(Integer)
    keyword_classif_cached_tokens = Column(Integer)
    keyword_classif_output_tokens = Column(Integer)
    keyword_classif_thinking_tokens = Column(Integer)

    # ── Exclusion processing (0–1 call) ────────────────────────────
    exclusion_elapsed_s = Column(Float)
    exclusion_input_tokens = Column(Integer)
    exclusion_cached_tokens = Column(Integer)
    exclusion_output_tokens = Column(Integer)
    exclusion_thinking_tokens = Column(Integer)

    # ── Totals ─────────────────────────────────────────────────────
    total_elapsed_s = Column(Float)
    total_input_tokens = Column(Integer)
    total_cached_tokens = Column(Integer)
    total_output_tokens = Column(Integer)
    total_thinking_tokens = Column(Integer)
