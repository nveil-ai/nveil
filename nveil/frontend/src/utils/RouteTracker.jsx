// SPDX-FileCopyrightText: 2025 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { trackPageView } from "./analytics";

const RouteTracker = () => {
  const location = useLocation();

  useEffect(() => {
    // Push a virtual pageview to the dataLayer on every route change.
    // GTM fires GA4 / Reddit / LinkedIn page-view tags from this event.
    trackPageView(location.pathname + location.search);
  }, [location]);

  return null;
};

export default RouteTracker;
