// SPDX-FileCopyrightText: 2025 NVEIL SAS
// SPDX-FileContributor: Guillaume Franque
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import { createContext, useContext, useState, useEffect, useRef, useCallback, useMemo } from "react";

const AuthContext = createContext();

/**
 * Custom hook to access the authentication context.
 *
 * @throws {Error} If used outside of an AuthProvider.
 * @returns {object} The authentication context value.
 */
export const useAuth = () => {
	const context = useContext(AuthContext);
	if (!context) {
		throw new Error('useAuth must be used within an AuthProvider');
	}
	return context;
}

/**
 * AuthProvider component that supplies authentication context to its children.
 *
 * Handles user authentication state, CSRF token management, secure API requests,
 * login, logout, and user fetching. Provides context values for user data,
 * authentication status, secure request helper, login/logout functions, loading state,
 * and a method to refetch user data.
 *
 * @component
 * @param {Object} props
 * @param {React.ReactNode} props.children - Child components that consume the authentication context.
 * @returns {JSX.Element} The AuthContext provider wrapping its children.
 *
 * @context
 * @property {Object|null} user - The authenticated user object or null if not authenticated.
 * @property {Function} logout - Function to log out the current user.
 * @property {boolean} isAuthenticated - Whether a user is currently authenticated.
 * @property {Function} secureRequest - Helper for making API requests with CSRF and credentials.
 * @property {Function} login - Function to log in a user with credentials.
 * @property {boolean} loading - Whether authentication state is being determined.
 * @property {Function} refetchUser - Function to manually refetch the current user.
 */
export const AuthProvider = ({ children }) => {
	const [user, setUser] = useState(null);
	const [isGuest, setIsGuest] = useState(false);
	const [loading, setLoading] = useState(true);
	const [showAuthModal, setShowAuthModal] = useState(false);
	const [profileComplete, setProfileComplete] = useState(true);
	const [missingFields, setMissingFields] = useState([]);
	const [googleAuthClientId, setGoogleAuthClientId] = useState(null);
	const csrfTokenRef = useRef(null);
	const isRefreshing = useRef(false);
	const accessExpiryRef = useRef(null);

	// Track last successful refresh time to allow proactive refresh when we can't
	// reliably inspect the access token expiry (fallback mechanism).
	const lastRefreshRef = useRef(null);

	// Helpers to inspect access token expiry (if stored in a cookie).
	const getCookie = (name) => {
		if (typeof document === 'undefined') return null;
		const match = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
		return match ? decodeURIComponent(match[2]) : null;
	};

	const findAccessTokenCookie = () => {

		const v = getCookie("access_token");
		if (v) {
			return v;
		}
		else {

			return null;
		}
	};

	const parseJwtPayload = (token) => {
		try {
			const parts = token.split('.');
			if (parts.length < 2) return null;
			const payload = parts[1].replace(/-/g, '+').replace(/_/g, '/');
			const json = atob(payload);
			try { return JSON.parse(decodeURIComponent(escape(json))); }
			catch (e) { return JSON.parse(json); }
		} catch (e) {
			return null;
		}
	};

	const tokenWillExpireSoon = (thresholdMs = 2 * 60 * 1000) => {
		// Prefer server-provided expiry (ms) when available
		if (accessExpiryRef.current) {
			const expMs = accessExpiryRef.current;
			return (Date.now() + thresholdMs) >= expMs;
		}
		const token = findAccessTokenCookie();
		if (!token) return null;
		const payload = parseJwtPayload(token);
		if (!payload || !payload.exp) return null;
		const expMs = payload.exp * 1000;
		return (Date.now() + thresholdMs) >= expMs;
	};

	/**
	 * Fetches a CSRF token from the server and updates the state with the token.
	 *
	 * Makes a GET request to the `/server/auth/csrf` endpoint, expecting a JSON response
	 * containing a `csrfToken` property. If the response is not JSON, a warning is logged.
	 * Handles errors by logging them to the console.
	 *
	 * @async
	 * @function fetchCSRFToken
	 * @returns {Promise<void>} Resolves when the CSRF token has been fetched and set, or logs an error if the request fails.
	 */
	const fetchCSRFToken = async () => {
		try {
			const response = await fetch('/server/auth/csrf', {
				method: 'GET',
				credentials: 'include',
				headers: {
					'Content-Type': 'application/json',
				}
			});
			if (response.ok) {
				const contentType = response.headers.get('content-type');
				if (contentType && contentType.includes('application/json')) {
					const data = await response.json();
					csrfTokenRef.current = data.csrfToken;
					return data.csrfToken;
				} else {
					console.warn('CSRF endpoint did not return JSON');
				}
			}
		}
		catch (error) {
			console.debug('Failed to fetch CSRF token', error);
		}
		return null;
	}

	const handleTokenRefresh = useCallback(async () => {
		if (isRefreshing.current) {
			throw new Error('Token refresh already in progress');
		}
		isRefreshing.current = true;
		try {
			const response = await fetch('/server/auth/refresh', {
				method: 'POST',
				credentials: 'include',
				headers: {
					'Content-Type': 'application/json',
					'X-Requested-With': 'XMLHttpRequest',
					...(csrfTokenRef.current && { 'X-CSRF-Token': csrfTokenRef.current })
				}
			});
			// console.log('Token refresh : ', response);
			if (response.ok) {
				// parse body to extract access expiry if provided by server
				try {
					const data = await response.json();
					if (data && data.access_token_expiry) {
						accessExpiryRef.current = Number(data.access_token_expiry) * 1000;
						// console.log('Updated access token expiry to ', new Date(accessExpiryRef.current).toISOString());
					}
				} catch (e) {
					// ignore parse errors; server may not return JSON
				}
				// record successful refresh time
				lastRefreshRef.current = Date.now();
				return true;
			}
			else {
				// If the refresh endpoint explicitly rejects the refresh (invalid/expired
				// refresh token) we should clear user state and force a full re-auth.
				if (response.status === 401 || response.status === 403) {
					// console.warn('Refresh endpoint returned unauthorized; clearing session', response.status);
					setUser(null);
					csrfTokenRef.current = null;
					if (window.sessionStorage) window.sessionStorage.clear();
					// throw new Error('Token refresh unauthorized');
				}
				else {
					// For other non-OK statuses (network/server errors), do not clear user here —
					// these are transient and will be handled by callers (they may retry).
					throw new Error('Token refresh failed with status: ' + response.status);
				}
			}
		}
		catch (error) {
			// Don't aggressively clear user on network or unexpected errors here.
			// The caller (secureRequest / fetchUser) decides how to handle failures.
			throw error;
		}
		finally {
			isRefreshing.current = false;
		}
	}, []);

	/**
	 * Sends a secure HTTP request with default headers and CSRF protection.
	 *
	 * @async
	 * @function
	 * @param {string} url - The URL to which the request is sent.
	 * @param {Object} [options={}] - Additional fetch options (e.g., method, body, headers).
	 * @param {Object} [options.headers] - Additional headers to include in the request.
	 * @returns {Promise<Response>} The fetch API Response object.
	 * @throws {Error} If the response status is 401 (Unauthorized) or if the request fails.
	 */
	const secureRequest = useCallback(async (url, options = {}) => {
		const defaultHeaders = {
			'X-Requested-With': 'XMLHttpRequest',
		};
		// Don't set Content-Type for FormData — let the browser set multipart boundary
		if (!(options.body instanceof FormData)) {
			defaultHeaders['Content-Type'] = 'application/json';
		}
		if (csrfTokenRef.current) {
			defaultHeaders['X-CSRF-Token'] = csrfTokenRef.current;
		}
		const mergedHeaders = { ...defaultHeaders, ...options.headers };
		// Remove any explicitly-undefined headers
		for (const key of Object.keys(mergedHeaders)) {
			if (mergedHeaders[key] === undefined) delete mergedHeaders[key];
		}
		const config = {
			credentials: 'include',
			...options,
			headers: mergedHeaders,
		};

		// Proactive pre-request refresh: prefer to inspect the access_token expiry when available.
		// Skip preflight for auth endpoints and when explicitly disabled via _noPreflight option.
		const preflightDisabled = options._noPreflight === true;
		const isAuthEndpoint = url.includes('/auth/login') || url.includes('/auth/refresh') || url.includes('/auth/csrf');
		const REFRESH_THRESHOLD_MS = 13 * 60 * 1000; // fallback threshold
		if (!preflightDisabled && !isAuthEndpoint) {
			const willExpire = tokenWillExpireSoon(2 * 60 * 1000); // 2 minute window
			if (willExpire === true) {
				try {
					await handleTokenRefresh();
				} catch (err) {
					console.debug('Preflight token refresh (by expiry) failed:', err);
				}
			}
			else if (willExpire === null) {
				// couldn't inspect token; fallback to timestamp-based preflight
				const last = lastRefreshRef.current;
				if (!last || (Date.now() - last) > REFRESH_THRESHOLD_MS) {
					try {
						await handleTokenRefresh();
					} catch (err) {
						console.debug('Preflight token refresh (by timestamp) failed:', err);
					}
				}
			}
		}

		let response = fetch(url, config).then(async function (response) {
			if (response.status === 401 && !options._retry) {
				if (url.includes('/auth/login') ||
					url.includes('/auth/refresh') ||
					url.includes('/auth/csrf')) {
					return response;
				}
				try {
					await handleTokenRefresh();
					const retryConfig = {
						...config,
						_retry: true
					};
					response = await fetch(url, retryConfig);
				}
				catch (refreshError) {
					return response;
				}
			}
			return response;
		}).catch(function (error) {
			console.debug('API request failed:', error);
			throw error;
		});
		return response;
	}, []);

	const applyUserPayload = useCallback((userData) => {
		if (!userData) {
			setUser(null);
			setIsGuest(false);
			return false;
		}
		if (userData.access_token_expiry) {
			accessExpiryRef.current = Number(userData.access_token_expiry) * 1000;
			lastRefreshRef.current = Date.now();
		}
		const userIsGuest = userData.is_guest === true;
		setIsGuest(userIsGuest);

		if (!userIsGuest) {
			setProfileComplete(userData.profile_complete !== false);
			setMissingFields(userData.missing_fields || []);
			try { localStorage.setItem('guestblocked', '1'); } catch (_) {}
		} else {
			setProfileComplete(true);
			setMissingFields([]);
		}

		const sanitizedUser = {
			id: userData.id,
			email: userData.email,
			name: userData.name?.replace(/<[^>]*>/g, ''),
			room_id: userData.room_id,
			is_guest: userIsGuest,
			license: userData.license,
			license_details: userData.license_details,
		};
		setUser(prevUser => {
			if (JSON.stringify(prevUser) !== JSON.stringify(sanitizedUser)) {
				return sanitizedUser;
			}
			return prevUser;
		});
		return true;
	}, []);

	/**
	 * Fetches the current authenticated user's data from the server.
	 * If successful, sanitizes and sets the user state with the user's id, email, and name (with HTML tags removed).
	 * If the request fails or returns a non-ok response, sets the user state to null.
	 * Handles errors and ensures loading state is updated after the request.
	 *
	 * @async
	 * @function fetchUser
	 * @returns {Promise<boolean>} Returns true if user was found and authenticated, false otherwise.
	 */
	const fetchUser = useCallback(async () => {
		try {
			const res = await secureRequest('/server/auth/me')
			if (res.ok) {
				const userData = await res.json();
				return applyUserPayload(userData);
			}
			else {
				if (res.status === 401 || res.status === 403) {
					csrfTokenRef.current = null;
					if (window.sessionStorage) {
						window.sessionStorage.clear();
					}
				}
				setUser(null);
				setIsGuest(false);
				return false;
			}
		}
		catch (error) {
			console.debug('Error fetching user:', error);
			setUser(null);
			setIsGuest(false);
			return false;
		}
		finally {
			setLoading(false);
		}
	}, [applyUserPayload]);

	/**
	 * Authenticates a user with the provided credentials.
	 *
	 * @async
	 * @function
	 * @param {Object} credentials - The user's login credentials.
	 * @param {string} credentials.email - The user's email address.
	 * @param {string} credentials.password - The user's password.
	 * @returns {Promise<{success: boolean, error?: string}>} An object indicating the success status and an optional error message.
	 * @throws {Error} Throws an error if required fields are missing or if the email format is invalid.
	 */
	const login = useCallback(async (credentials) => {
		try {
			if (!credentials.email || !credentials.password) {
				throw new Error('Email and password are required');
			}
			const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
			if (!emailRegex.test(credentials.email)) {
				throw new Error('Invalid email form');
			}
			const formData = new URLSearchParams();
			formData.append('username', credentials.email);
			formData.append('password', credentials.password);
			const response = await secureRequest('/server/auth/login', {
				method: 'POST',
				headers: {
					'Content-Type': 'application/x-www-form-urlencoded',
				},
				body: formData,
			});
			if (response.ok) {
				const data = await response.json();

				// Check if password change is required (one_time_password)
				if (data.requires_password_change) {
					return {
						success: false,
						requires_password_change: true,
						email: data.email
					};
				}

				setIsGuest(false);

				await fetchUser();
				return {
					success: true,
					profile_complete: data.profile_complete,
					missing_fields: data.missing_fields,
					user: data.user
				};
			}
			else {
				const error = await response.json();
				throw new Error(error.detail || 'Login failed');
			}
		}
		catch (error) {
			console.error('Login error:', error);
			return { success: false, error: error.message };
		}
	}, []);

	/**
	 * Logs out the current user by sending a POST request to the logout API endpoint.
	 * On success or failure, clears user state, CSRF token, and session storage.
	 *
	 * @async
	 * @function logout
	 * @returns {Promise<void>} Resolves when logout process is complete.
	 */
	const logout = useCallback(async () => {
		try {
			await secureRequest('/server/auth/logout', {
				method: 'POST',
			});
		}
		catch (error) {
			console.error('Logout error:', error);
		}
		finally {
			setUser(null);
			csrfTokenRef.current = null;
			if (window.sessionStorage) {
				window.sessionStorage.clear();
			}
			window.location.href = '/';
		}
	}, []);

	const logoutAll = useCallback(async () => {
		try {
			await secureRequest('/server/auth/logout-all', {
				method: 'POST',
			});
		}
		catch (error) {
			console.error('Logout all error:', error);
		}
		finally {
			setUser(null);
			setIsGuest(false);
			csrfTokenRef.current = null;
			if (window.sessionStorage) {
				window.sessionStorage.clear();
			}
			window.location.href = '/';
		}
	}, []);

	/**
	 * Creates a guest session for unauthenticated users.
	 * Guest users get a pre-loaded sample dataset to explore the app.
	 * 
	 * @async
	 * @function createGuestSession
	 * @returns {Promise<boolean>} True if guest session created successfully.
	 */
	const createGuestSession = useCallback(async (token = null) => {
		try {
			let activeToken = token || csrfTokenRef.current;
			if (!activeToken) {
				activeToken = await fetchCSRFToken();
			}
			const response = await fetch('/server/auth/guest', {
				method: 'POST',
				credentials: 'include',
				headers: {
					'Content-Type': 'application/json',
					...(activeToken && { 'X-CSRF-Token': activeToken })
				}
			});
			if (response.ok) {
				const data = await response.json();
				setIsGuest(true);
				setUser({
					id: data.user?.id,
					email: data.user?.email,
					name: data.user?.name,
					is_guest: true,
				});
				return true;
			}
			return false;
		} catch (error) {
			console.error('Failed to create guest session:', error);
			return false;
		}
	}, []);

	useEffect(() => {
		// During pre-rendering (Puppeteer/snapshot generation), skip all auth
		// to avoid 401 console errors and junk guest sessions in the DB.
		if (typeof window !== 'undefined' && window.__PRERENDERING) {
			setLoading(false);
			return;
		}

		const initializeAuth = async () => {
			try {
				// Single origin round-trip for CSRF + user state. Falls back to the
				// legacy /csrf + /me pair if /bootstrap isn't reachable (older backend).
				const res = await fetch('/server/auth/bootstrap', {
					method: 'GET',
					credentials: 'include',
					headers: { 'Content-Type': 'application/json' },
				});
				if (res.ok) {
					const data = await res.json();
					if (data?.csrfToken) {
						csrfTokenRef.current = data.csrfToken;
					}
					if (data?.google_auth_client_id) {
						setGoogleAuthClientId(data.google_auth_client_id);
					}
					applyUserPayload(data?.user ?? null);
				} else {
					await fetchCSRFToken();
					await fetchUser();
					return;
				}
			}
			catch (error) {
				console.error('Auth initialization failed:', error);
			}
			finally {
				setLoading(false);
			}
		};
		initializeAuth();
	}, []);

	// Auto-open auth modal when a non-guest user has an incomplete profile
	useEffect(() => {
		if (user && !loading && !isGuest && !profileComplete) {
			setShowAuthModal(true);
		}
	}, [user, loading, isGuest, profileComplete]);

	useEffect(() => {
		if (user && !loading) {
			const interval = setInterval(() => {
				fetchUser().catch(() => {});
			}, 5 * 60 * 1000);
			return () => clearInterval(interval);
		}
	}, [user, loading]);

	useEffect(() => {
		const handleWebSocketMessage = (event) => {
			try {
				const data = JSON.parse(event.data);
				if (data.type === "force_logout" && data.reason === "password_changed") {
					// Clear local session and redirect to login
					setUser(null);
					csrfTokenRef.current = null;
					if (window.sessionStorage) {
						window.sessionStorage.clear();
					}
					// Show notification before redirect
					alert("Your password was changed from another device. Please log in again.");
					window.location.href = '/';
				}
			} catch (e) {
				// Ignore non-JSON messages
			}
		};

		// Add listener to existing WebSocket connection
		if (window.appWebSocket) {
			window.appWebSocket.addEventListener('message', handleWebSocketMessage);
			return () => {
				window.appWebSocket.removeEventListener('message', handleWebSocketMessage);
			};
		}
	}, []);

	const value = useMemo(() => ({
		user,
		logout,
		logoutAll,
		isAuthenticated: !!user,
		isGuest,
		profileComplete,
		missingFields,
		secureRequest,
		login,
		loading,
		refetchUser: fetchUser,
		createGuestSession,
		showAuthModal,
		setShowAuthModal,
		googleAuthClientId,
	}), [user, isGuest, profileComplete, missingFields, loading, showAuthModal,
		logout, logoutAll, secureRequest, login, fetchUser, createGuestSession,
		googleAuthClientId]);

	return (
		<AuthContext.Provider value={value}>
			{children}
		</AuthContext.Provider>
	);
};
