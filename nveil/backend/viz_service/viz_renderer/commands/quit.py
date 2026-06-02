# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

# commands/quit.py
from trame.app import get_server


def handle_quit(args):
    server = get_server(name="nveil")
    server.controller.shutdown()