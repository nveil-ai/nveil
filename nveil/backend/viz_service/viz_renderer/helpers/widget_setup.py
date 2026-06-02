# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

from typing import Optional

from trame_vuetify.widgets import vuetify3 as vuetify


def vcard(children=None, title: Optional[str] = None, **attrs):
    """
    Create a VCard and embed provided children inside it.

    """
    # allow passing children via children_list kwarg
    # create card by passing children as positional args so widgets are instantiated
    return vuetify.VCard(children=children, title=title, **attrs, elevation=0)