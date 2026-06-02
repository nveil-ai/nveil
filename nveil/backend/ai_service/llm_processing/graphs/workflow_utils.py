# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

import html
import re
from lxml import etree

from shared.service_client import ServiceClient
from logger import DEBUG, ERROR, WARNING, logger

from ..config import SERVER_HOST

_server_client = ServiceClient(verify=True)

def clean_message_content(
    raw: str,
) -> (
    str
):  # Might be temporary but required for the moment when the history is passed to the LLM
    """
    Cleans HTML content from a message string and converts it to plain text.
    """
    if not raw:
        return ""
    text = raw

    # Clean line breaks
    text = re.sub(r"<\s*br\s*/?>", "\n", text, flags=re.IGNORECASE)

    # Paragraphs -> double line breaks
    text = re.sub(r"</\s*p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*p[^>]*>", "", text, flags=re.IGNORECASE)

    # Titles -> double line breaks
    text = re.sub(r"<\s*h[1-6][^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</\s*h[1-6]\s*>", "\n", text, flags=re.IGNORECASE)

    # Lists
    text = re.sub(r"<\s*li[^>]*>", "- ", text, flags=re.IGNORECASE)
    text = re.sub(r"</\s*li\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*ul[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*ol[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</\s*ul\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</\s*ol\s*>", "\n", text, flags=re.IGNORECASE)

    # Remove all other tags
    text = re.sub(r"<[^>]+>", "", text)

    # DDecode HTML entities
    text = html.unescape(text)

    # Clean whitespace
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n", text)
    return text.strip()

def clean_raw_feedback_output(raw: str) -> str:
    # More operations will be added here as we identify common patterns in the raw LLM output that we want to clean up before displaying to users. For now, this is focused on ensuring any occurrence of the feedback URL is properly wrapped in an <a> tag, while avoiding double-wrapping if the LLM already included it.
    if not raw:
        return ""
    FEEDBACK_URL = "https://feedback.nveil.com/"
    FEEDBACK_LINK = f'<a href="{FEEDBACK_URL}">{FEEDBACK_URL}</a>'
    # Strip any existing <a> wrapper around the feedback URL (handles extra spaces, varied attrs)
    raw = re.sub(
        r'<a\s[^>]*href\s*=\s*["\']\s*' + re.escape(FEEDBACK_URL) + r'\s*["\'][^>]*>\s*' + re.escape(FEEDBACK_URL) + r'\s*</a>',
        FEEDBACK_URL,
        raw,
    )
    # Now wrap every bare occurrence
    raw = raw.replace(FEEDBACK_URL, FEEDBACK_LINK)
    return raw

def approximate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return max(1, len(text) // 4)


def format_message_history(
    response_message_history,
    clean: bool = True,
    nb_message_to_keep=None,
    max_tokens: int | None = None,
) -> str:
    message_history = []
    for msg in response_message_history:
        if msg["author_email"] == "bot@nveil.bob":
            message_history.append({"role": "ai", "content": msg["content"]})
        else:
            message_history.append({"role": "user", "content": msg["content"]})
    if max_tokens is not None:
        selected = []
        token_count = 0
        for entry in reversed(message_history):
            content_for_count = entry.get("content", "")
            if entry.get("role") == "ai":
                content_for_count = clean_message_content(content_for_count)
            msg_tokens = approximate_tokens(content_for_count)
            if not selected or token_count + msg_tokens <= max_tokens:
                selected.append(entry)
                token_count += msg_tokens
            else:
                break
        message_history = list(reversed(selected))
        logger().logp(DEBUG, f"[format_message_history] {token_count} tokens kept, corresponding to {len(message_history)} messages")
    elif nb_message_to_keep is not None:
        message_history = message_history[-min(nb_message_to_keep, len(message_history)):]
    formatted_history = ""
    for entry in message_history:
        role = entry.get("role", "user").upper()
        content = entry.get("content", "")
        if clean and role != "USER":
            content = clean_message_content(content)
        formatted_history += f"[{role}]: {content}\n\n"
    return formatted_history


def filter_xml_by_user_request(user_message: str, xml_data: str) -> str:
    """
    Filter the XML data to retain only the fields mentioned in the user message.
    """
    user_message_norm = user_message.lower()

    root = etree.fromstring(xml_data.encode("utf-8") if isinstance(xml_data, str) else xml_data)

    # Run through each rawData and its fields
    for rawData in root.findall(".//rawData"):
        fields = rawData.find("fields")
        if fields is not None:
            for field in list(
                fields.findall("field")
            ):  # create a copy of the list for safe removal
                field_name = field.get("name", "").lower()

                # Check if the field name is explicitly mentioned in the user message
                # Surround the field name with word boundaries to avoid false positives (e.g., "Age" in "Message")
                pattern = r"\b" + re.escape(field_name) + r"\b"
                if not re.search(pattern, user_message_norm):
                    fields.remove(field)

    # Indent the XML for readability
    indent_xml(root)

    return etree.tostring(root, encoding="unicode")


def indent_xml(elem, level=0):
    """Add readable indentation to the XML"""
    i = "\n" + level * "\t"
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "\t"
        for child in elem:
            indent_xml(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = i
    if level and (not elem.tail or not elem.tail.strip()):
        elem.tail = i


def format_xml_data_to_tabular(xml_content: str, user_message: str, complete_description: bool = False) -> str:
    """
    Format XML data into a tabular string representation.
    """
    MAX_FIELD_NUMBER = 100
    nb_field = count_fields(xml_content)
    if nb_field > MAX_FIELD_NUMBER and not complete_description:
        xml_content = filter_xml_by_user_request(user_message, xml_content)
    root = etree.fromstring(xml_content.encode("utf-8") if isinstance(xml_content, str) else xml_content)
    output_lines = []
    for datas in root.findall("datas"):
        for data_type in ["rawData", "transformedData"]:
            for data in datas.findall(data_type):
                id = data.get("id")
                name = data.get("name")
                output_lines.append(f"=== Data (dataId={id} ; {name}) ===")
                if complete_description:
                    output_lines.append("| ID | NAME | TYPE | MIN | MAX | DISCRETE |")
                    output_lines.append("| --- | --- | --- | --- | --- | --- |")
                else:
                    output_lines.append("| ID | NAME | TYPE |")
                    output_lines.append("| --- | --- | --- |")

                for field in data.find("fields").findall("field"):
                    fid = field.get("id")
                    fname = field.get("name")
                    ftype = field.get("dataType")
                    if complete_description:
                        fmin = field.get("fieldMin", "")
                        fmax = field.get("fieldMax", "")
                        discrete = field.get("discrete", "UNDEFINED")
                        output_lines.append(f"| {fid} | {fname} | {ftype} | {fmin} | {fmax} | {discrete} |")
                    else:
                        output_lines.append(f"| {fid} | {fname} | {ftype} |")

            output_lines.append("")

    return "\n".join(output_lines).strip()


def remove_data_attribute(xml_str: str) -> str:
    # Remove the <datas>...</datas> block (non-greedy, multiline)
    return re.sub(r"<datas>.*?</datas>\s*", "", xml_str, flags=re.DOTALL)


def count_fields(xml_str: str) -> int:
    root = etree.fromstring(xml_str.encode("utf-8") if isinstance(xml_str, str) else xml_str)
    field_count = 0
    for raw_data in root.findall("rawData"):
        fields = raw_data.find("fields")
        if fields is not None:
            field_count += len(fields.findall("field"))
    return field_count


def filter_xml_by_channels(xml_data: str) -> str:
    """
    Keep only the fields in rawData that are referenced in channels.
    """
    root = etree.fromstring(xml_data.encode("utf-8") if isinstance(xml_data, str) else xml_data)

    used_fields = set()
    for channel in root.findall(".//channels//*"):
        data_id = channel.get("dataId")
        field_id = channel.get("fieldId")
        if data_id and field_id and field_id.isdigit():
            used_fields.add((data_id, field_id))

    for rawData in root.findall(".//rawData"):
        data_id = rawData.get("id")
        fields = rawData.find("fields")
        if fields is not None:
            for field in list(fields.findall("field")):
                field_id = field.get("id")
                if (data_id, field_id) not in used_fields:
                    fields.remove(field)

    indent_xml(root)
    return etree.tostring(root, encoding="unicode")


def remove_empty_channels(xml_input):
    """
    Remove channels with label, dataId, and fieldId all set to "UNDEFINED" from the XML input (sometimes generated by the viz xml generator).
    """
    root = etree.fromstring(xml_input.encode("utf-8") if isinstance(xml_input, str) else xml_input)
    removed_ids = set()

    channels_root = root.find(".//channels")
    if channels_root is not None:
        for group in channels_root:
            for channel in list(group):
                label = channel.get('label')
                data_id = channel.get('dataId')
                field_id = channel.get('fieldId')

                if label == "UNDEFINED" and field_id in ["UNDEFINED", "0"]:
                    cid = channel.get('id')
                    if cid:
                        removed_ids.add(cid)
                    group.remove(channel)


    marks_container = root.find(".//marks")
    if marks_container is not None:
        for mark in marks_container:
            for attr, value in mark.attrib.items():
                if value in removed_ids and attr != "id":
                    mark.set(attr, "HANDLED_BY_MODE")

    return etree.tostring(root, encoding='unicode', method='xml')

def combine_inputs(info_dict) -> str:
    """Combine both fields from additional information into a single string."""
    if info_dict is None:
        return ""
    return ';'.join(filter(None, [values for _, values in info_dict.items()]))

def merge_additional_info(d1, d2, sep=" ; "):
    if d1 is None:
        return d2
    if d2 is None:
        return d1
    keys = set(d1) | set(d2)
    out = {}
    for k in keys:
        parts = []
        for v in (d1.get(k), d2.get(k)):
            if v not in (None, ""):
                parts.append(str(v))
        if parts:
            out[k] = sep.join(parts)
        else:
            out[k] = ""  
    return out

async def get_additional_info(user_id: str, room_id: str, db) -> dict:
    """
    Update the existing additional information with new information for a specific field.
    Both existing_info and new_info are dictionaries.
    The function concatenates values for overlapping keys.
    """
    # Load the existing room related information from .json file
    url = f"https://{SERVER_HOST}:8000/server/files/get_metadata"
    resp = await _server_client.get(
        url,
        params={"metadata_name": "additional_info"},
        cookies={"room_id": room_id},
    )
    if resp.ok and isinstance(resp.data, dict):
        room_related_info = resp.data.get("additional_info", "")
    else:
        room_related_info = ""
    # Load the existing user related information from user db
    user_related_info = await db.get_user_compl_info(user_id)
    if user_related_info is None:
        user_related_info = ""

    return {
        "room_related": room_related_info,
        "user_related": user_related_info
    }


async def set_additional_info(user_id: str, room_id: str, new_info: dict, db):
    """
    Append new_info to existing 'additional_info' metadata for the room, then
    persist updated user info in DB. Uses server /server/files/set_metadata endpoint.
    """
    if len(new_info) == 0:
        return  
    room_info = new_info.get("room_related", "")
    user_info = new_info.get("user_related", "")

    try:
        url = f"https://{SERVER_HOST}:8000/server/files/set_metadata"
        payload = {"additional_info": room_info}
        resp = await _server_client.post(
            url,
            json=payload,
            cookies={"room_id": room_id},
        )
        if not resp.ok:
            logger().logp(ERROR, f"Failed to set room metadata (status={resp.status_code}): {resp.error}")
        else:
            logger().logp(DEBUG, "Updated room additional_info metadata successfully.")
    except Exception as e:
        logger().logp(ERROR, f"Exception while calling set_metadata: {e}")

    try:
        await db.set_user_compl_info(user_id, user_info)
    except Exception as e:
        logger().logp(ERROR, f"Failed to update user complementary info: {e}")
