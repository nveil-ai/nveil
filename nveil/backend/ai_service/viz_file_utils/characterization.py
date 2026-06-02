# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

import csv
import io
import os
import re
from typing import Optional

from llm_processing.node_config import get_node_config
from llm_processing.prompt import CSVCharacterization
from logger import ERROR, INFO, WARNING, logger
from pydantic import BaseModel, ConfigDict
from shared.llm_config import LLMConfig, build_chat_model


class CSVFileStruct(BaseModel):
    model_config = ConfigDict(extra="forbid")
    header: bool
    fieldSeparator: str
    recordSeparator: str


def ai_characterisation(sample, llm_config: Optional[LLMConfig] = None):
    """Run the CSV characterization LLM.

    `llm_config` carries the user's provider + api_key (set in the SDK
    headers, propagated by the endpoint). When None — typical for the
    file-upload pipeline where we don't yet plumb per-request config —
    we fall back to the server's default Gemini env credentials.
    """
    if llm_config is None:
        llm_config = LLMConfig.from_env()

    cfg = dict(get_node_config("csv_characterization", llm_config.provider))
    model = cfg.pop("model")

    llm = build_chat_model(llm_config, model=model, **cfg)
    llm_structured = llm.with_structured_output(CSVFileStruct, include_raw=True)
    chat_template, variables = CSVCharacterization().build(sample=sample)
    chain = chat_template | llm_structured
    result = chain.invoke(variables)
    response = result.get("parsed")
    raw = result.get("raw")
    if raw and raw.usage_metadata:
        logger().logp(INFO, f"Usage metadata: {dict(raw.usage_metadata)}")
    if response and isinstance(response, CSVFileStruct):
        return response
    else:
        raise ValueError("AI characterization did not return a valid CSVFileStruct.")


def split_csv_line(line: str, delimiter: str):
    """
    Parse CSV lines with the given delimiter, considering quotes.
    """
    reader = csv.reader(io.StringIO(line), delimiter=delimiter, quotechar='"')
    return next(reader)


import csv

def detect_skip_lines_smart(lines, delimiter_list, tolerance: int = 1, min_ok_lines: int = 2) -> int:
    """
    Detects start of data by parsing full CSV logic (handling multiline quotes).
    """
    # On rejoint tout pour laisser le module CSV gérer les retours à la ligne entre guillemets
    full_content = "\n".join(lines)
    
    for delimiter in delimiter_list:
        try:
            # On demande au module CSV de lire proprement
            reader = csv.reader(full_content.splitlines(keepends=True), delimiter=delimiter)
            parsed_rows = list(reader) # Attention: charge tout en mémoire. Pour des gros fichiers, utiliser islice.
            
            if not parsed_rows:
                continue

            for i, row in enumerate(parsed_rows):
                current_len = len(row)
                
                # Si la ligne est vide ou presque, on continue
                if current_len <= 1: 
                    continue
                
                ok = 0
                # On regarde les lignes logiques suivantes
                for j in range(i + 1, min(i + 6, len(parsed_rows))):
                    next_row_len = len(parsed_rows[j])
                    if abs(next_row_len - current_len) <= tolerance:
                        ok += 1
                
                if ok >= min_ok_lines:
                    return i # C'est le bon index de LIGNE LOGIQUE
                    
        except Exception:
            continue
            
    return 0

def remove_skiplines(filepath, skip_lines, buffer_size=8192):
    """
    Deletes the first `skip_lines` lines from a file efficiently using buffered reading and writing.

    Args:
        filepath: Path to the file to modify
        skip_lines: Number of lines to delete
        buffer_size: Size of the read buffer (in bytes)

    Returns:
        bool: True if modifications were made, else False
    """
    if skip_lines <= 0:
        return False

    temp_file = str(filepath) + ".tmp"
    try:
        with open(filepath, "rb") as f_in:
            # Ignore lines to skip
            lines_skipped = 0
            while lines_skipped < skip_lines:
                line = f_in.readline()
                if not line:  # End of file
                    return False  # Nothing to modify
                lines_skipped += 1

            # Current position = start of data to keep
            start_pos = f_in.tell()

            with open(temp_file, "wb") as f_out:
                f_in.seek(start_pos)

                # Copy the rest of the file in chunks
                while True:
                    chunk = f_in.read(buffer_size)
                    if not chunk:
                        break
                    f_out.write(chunk)

        os.replace(temp_file, filepath)
        return True

    except Exception as e:
        logger().logp(ERROR, f"Erreur lors de la suppression des lignes: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False


def analyse_csv(
    filepath: str,
    target_record_sep: str = "\n",
    llm_config: Optional[LLMConfig] = None,
) -> dict:
    """
    Analyzes a CSV file and returns a dictionary corresponding to the File type.
    """
    result = {
        "header": False,
        "fieldSeparator": None,
        "recordSeparator": None,
        "skipLines": 0,
        "modified": False,
    }
    fallback_charac = {
        "header": True,
        "fieldSeparator": ",",
        "recordSeparator": "\n",
        "skipLines": 0,
        "modified": False,
    }
    # TEMPORARY, to avoid AI analysis on Excel exports
    is_built_from_excel = bool(
        re.search(r"sheet\d+_table\d+\.csv", str(filepath), re.IGNORECASE)
    )

    # First pass: read small chunks to detect delimiters and structure
    usual_del = [",", ";", "\t", "|"]

    # Read only a sample of the file for initial analysis
    sample_size = 10240  # Read 10KB initially
    sample_lines = []
    newlines = None

    with open(filepath, "r", encoding="utf-8", errors="replace", newline=None) as f:
        # Read a limited number of lines for skip line detection
        for _ in range(50):  # Limiting to 50 lines for skip detection
            line = f.readline()
            if not line:
                break
            sample_lines.append(line)

        # Save the type of line endings detected
        f.seek(0)
        f.read(min(sample_size, os.path.getsize(filepath)))
        newlines = f.newlines

    # Detect skip lines using the sample we've already read
    result["skipLines"] = detect_skip_lines_smart(
        sample_lines, usual_del
    )

    # Use only the relevant lines after skipping
    useful_lines = sample_lines[
        result["skipLines"] : min(10 + result["skipLines"], len(sample_lines))
    ]

    try:
        # Analyze CSV structure from the useful lines
        sample = "".join(useful_lines)
        if is_built_from_excel:
            result["fieldSeparator"] = ","
            dialect = csv.Sniffer().sniff(sample, delimiters=[","])
            result["header"] = csv.Sniffer().has_header(sample)
        else:
            dialect = csv.Sniffer().sniff(sample, delimiters=usual_del)
            result["fieldSeparator"] = dialect.delimiter
            result["header"] = csv.Sniffer().has_header(sample)

        # Process the newlines information
        if isinstance(newlines, str):
            result["recordSeparator"] = newlines.encode().decode("unicode_escape")
        else:
            result["recordSeparator"] = dialect.lineterminator.encode().decode(
                "unicode_escape"
            )

    except Exception as e:
        if is_built_from_excel:
            logger().logp(
                ERROR,
                "A CSV built from an excel export has not been characterized heuristically. This should not happen.",
            )
        logger().logp(
            WARNING,
            f"Field separator could not be detected using heuristic rules: {e}. Using AI for analysis.",
        )
        # Only read a new sample if the previous approach failed
        with open(filepath, "rb") as f:
            f.seek(0)  # Ensure we're at the start
            binary_sample = f.read(sample_size)
        try:
            result_bis = ai_characterisation(binary_sample, llm_config=llm_config)
        except:
            logger().logp(
                ERROR,
                "AI characterization failed. Using fallback characteristics.",
            )
            return fallback_charac

        # Consistency check
        if result_bis.fieldSeparator in usual_del:
            logger().logp(
                WARNING,
                "Model detected a standard separator that should've been detected earlier.",
            )

        result["fieldSeparator"] = result_bis.fieldSeparator
        # Redetect skip lines with the new separator
        result["skipLines"] = detect_skip_lines_smart(
            sample_lines, [result_bis.fieldSeparator]
        )
        result["header"] = result_bis.header
        result["recordSeparator"] = result_bis.recordSeparator.encode().decode(
            "unicode_escape"
        )

    if result["skipLines"] > 0:
        modified = remove_skiplines(filepath, result["skipLines"])
        if modified:
            result["modified"] = True
            result["skipLines"] = 0  # After removal, no lines to skip

    return result
