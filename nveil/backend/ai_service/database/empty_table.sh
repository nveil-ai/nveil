# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

sudo -u postgres psql -d state -c "DELETE FROM state_schema.user_state;"