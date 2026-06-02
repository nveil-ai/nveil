// SPDX-FileCopyrightText: 2025 NVEIL SAS
// SPDX-FileContributor: Guillaume Franque
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { useEffect } from 'react';
import CookieBanner from './Components/CookieBanner';
import { CookiesProvider } from 'react-cookie';
import RouteTracker from "./utils/RouteTracker";
import NavBar from './NavBar/NavBar';
import { AuthProvider } from './Auth/AuthContext';
import { RoomProvider } from './Room/RoomContext';
import { WebSocketProvider } from './Chat/WebSocketContext';
import NotFound from './NotFound/NotFound';
import { Button as AriaButton, Text as AriaText, UNSTABLE_Toast as Toast, UNSTABLE_ToastContent as ToastContent, UNSTABLE_ToastQueue as ToastQueue, UNSTABLE_ToastRegion as ToastRegion } from 'react-aria-components'

import { Profiler, Suspense, lazy, useState } from 'react';
import Loading from './Components/Loading';
import { getExtensionRoutes, onExtensionsLoaded } from './extensions';
// import Home from "./Home/Home";
const Home = lazy(() => import("./Home/Home"));

// Lazy load route components
const Settings = lazy(() => import("./Settings/Settings"));
const Explore = lazy(() => import("./Explore/Explore"));
const Feedback = lazy(() => import("./Feedback/Feedback"));
const DataManager = lazy(() => import("./Data/DataManager"));
const DashboardList = lazy(() => import("./Dashboard/DashboardList"));
const DashboardView = lazy(() => import("./Dashboard/DashboardView"));


// Define the type for your toast content.

export const queue = new ToastQueue();

export default function App() {
	const [, setExtLoaded] = useState(false);
	useEffect(() => { onExtensionsLoaded(() => setExtLoaded(true)); }, []);

	function onRenderCallback(
		id, // the "id" prop of the Profiler tree that has just committed
		phase, // either "mount" (if the tree just mounted) or "update" (if it re-rendered)
		actualDuration, // time spent rendering the committed update
		baseDuration, // estimated time to render the entire subtree without memoization
		startTime, // when React began rendering this update
		commitTime, // when React committed this update
		interactions // the Set of interactions belonging to this update
	) {
		// console.log({id, phase, actualDuration, baseDuration, startTime, commitTime, interactions});
	}
	return (
		<>
			<ToastRegion queue={queue}>
				{({ toast }) => (
					<Toast toast={toast}>
						<ToastContent>
							<AriaText slot="title">{toast.content.title}</AriaText>
							<AriaText slot="description">{toast.content.description}</AriaText>
						</ToastContent>
						<AriaButton slot="close">
							x
						</AriaButton>
					</Toast>
				)}
			</ToastRegion>
			<CookiesProvider>
				<CookieBanner />
			</CookiesProvider>
			<AuthProvider>
				<Router>
					<WebSocketProvider>
						<RoomProvider>
							<RouteTracker />
							<NavBar />
							<Suspense fallback={<Loading />}>
								<Routes>
									<Route path="/" element={<Home />} />
									<Route path="/room/:roomToken" element={<Home />} />
									<Route path="/settings" element={<Settings />} />
									<Route path="/explore" element={<Explore />} />
									<Route path="/feedback" element={<Feedback />} />
									<Route path="/data" element={<DataManager />} />
									<Route path="/dashboards" element={<DashboardList />} />
									<Route path="/dashboard/:dashboardToken" element={<DashboardView />} />
									{/* Extension-provided routes (billing, etc. from @nveil/cloud-frontend) */}
									{getExtensionRoutes().map(r => (
										<Route key={r.path} path={r.path} element={<r.element />} />
									))}
									<Route path="*" element={<NotFound />} />
								</Routes>
							</Suspense>
						</RoomProvider>
					</WebSocketProvider>
				</Router>
			</AuthProvider>
			{/* </Profiler> */}
		</>
	);
}
