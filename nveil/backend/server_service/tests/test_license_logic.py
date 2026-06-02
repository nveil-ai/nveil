# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

from unittest.mock import MagicMock, patch
import pytest
from fastapi import Request

stripe = pytest.importorskip("stripe", reason="stripe not installed")


def _fake_get_secret(key, default=None):
    """Return sensible test defaults for each secret key."""
    defaults = {"FILE_PORT": "8200", "FILE_HOST": "localhost", "DATABASE_SCHEMA": "public"}
    return defaults.get(key, default or "fake_key")


with patch('stripe.api_key', 'fake_key'):
    with patch('utils.get_secret', side_effect=_fake_get_secret):
        try:
            from nveilplugin.billing.stripe_router import create_checkout_session
        except ImportError:
            pytest.skip("nveilplugin not installed", allow_module_level=True)

@pytest.mark.asyncio
async def test_create_checkout_session_is_monthly_logic():
    request = MagicMock(spec=Request)
    request.json.return_value = {"price_id": "price_123"}
    request.base_url = "http://localhost"

    current_user = MagicMock()
    current_user.id = "user_123"
    current_user.email = "test@example.com"

    mock_price = MagicMock()
    mock_price.recurring.interval = "month"

    with patch('stripe.Price.retrieve', return_value=mock_price) as mock_retrieve:
        with patch('stripe.checkout.Session.create') as mock_session_create:
            mock_session_create.return_value = MagicMock(url="http://stripe.com/session")
            response = await create_checkout_session(request, current_user)
            mock_retrieve.assert_called_once_with("price_123")
            assert response["url"] == "http://stripe.com/session"

    mock_price.recurring.interval = "year"
    with patch('stripe.Price.retrieve', return_value=mock_price):
        with patch('stripe.checkout.Session.create') as mock_session_create:
            mock_session_create.return_value = MagicMock(url="http://stripe.com/session")
            response = await create_checkout_session(request, current_user)
            assert response["url"] == "http://stripe.com/session"
