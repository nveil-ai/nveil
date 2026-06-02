# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

class ExclusionFactBuilder:
    """
    Builds ASP exclusion facts from (selector, value, scope).
    """
    def __init__(self):
        self._registry = {}
        for name in dir(self):
            if name.startswith("build_") and name not in ("build_asp_fact","build_generic"):
                sel = name.removeprefix("build_")
                self._registry[sel] = getattr(self, name)

    def build_fieldid(self, value: str, scope: str) -> list[str]:
        # value format: "dataId,fieldId"
        if "," not in value:
            return []
        data_id, field_id = [x.strip() for x in value.split(",", 1)]
        return [f'exclusion_field({data_id},{field_id},"{scope}").']

    def build_dataid(self, value: str, scope: str) -> list[str]:
        return [f'exclusion_data({value},"{scope}").']

    def build_discrete(self, value: str, scope: str) -> list[str]:
        if value.lower().strip() == "true":
            return [f'exclusion_discrete("{scope}").']
        return []

    def build_scaletype(self, value: str, scope: str) -> list[str]:
        return [f'exclusion_scaleType("{value}","{scope}").']

    def build_colorpalette(self, value: str, scope: str) -> list[str]:
        return [f'exclusion_colorPalette("{value}","{scope}").']

    def build_marktype(self, value: str, scope: str) -> list[str]:
        return [f'exclusion_markType({value},"{scope}").']

    def build_interpolation(self, value: str, scope: str) -> list[str]:
        return [f'exclusion_interpolation("{value}","{scope}").']

    def build_generic(self, selector: str, value: str, scope: str) -> list[str]:
        return [f'exclusion_{selector}("{scope}","{value}").']

    def build_asp_fact(self, selector: str, value: str, scope: str) -> list[str]:
        sel = selector.strip().lower()
        scope = scope if scope else "*"
        handler = self._registry.get(sel)
        if handler:
            facts = handler(value, scope)
            if facts:
                return facts
        return self.build_generic(sel, value, scope)

