// SPDX-FileCopyrightText: 2025 NVEIL SAS
// SPDX-FileContributor: Guillaume Franque
// SPDX-FileContributor: Pierre Jacquet
// SPDX-FileContributor: Clément Baraille
// SPDX-License-Identifier: AGPL-3.0-or-later

import styles from "./Chat.module.css";
import { DeepChat } from 'deep-chat-react';
import React, { useRef, useEffect, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from "../Auth/AuthContext";
import { useWebSocket } from "./WebSocketContext";
import deepChatStyles from "./DeepChat.css?raw";
import { trackEvent } from "../utils/analytics";
import PaletteModal from "../Components/Palette/PaletteModal";
import CustomInput from "./CustomInput";
import WelcomeMessage from "./WelcomeMessage";
import { queue } from "../App";

// --- Module-level constants ---

const DEEP_CHAT_STYLE = {
	overflowY: "auto",
	overflowX: "hidden",
	border: "0px",
	height: "100%",
	width: "auto",
	padding: "10px 0px 0px 10px",
	maxHeight: "unset",
	display: "flex",
	flexDirection: "column",
	boxSizing: "border-box"
};

const DEEP_CHAT_CHAT_STYLE = {
	backgroundColor: "#8b451300",
	borderRadius: "0px",
};

const DEEP_CHAT_MESSAGE_STYLES = {
	default: {
		shared: {
			outerContainer: { backgroundColor: "transparent" },
			innerContainer: { backgroundColor: "transparent" },
			bubble: { color: "white" },
		},
		ai: {
			bubble: {
				backgroundColor: "rgba(255,255,255,0.025)",
				border: "1px solid rgba(255,255,255,0.04)",
				borderRadius: "4px 20px 20px 20px",
				padding: "10px 14px",
				maxWidth: "calc(min(100%, 1000px))",
				marginRight: "0px",
			},
		},
		user: {
			bubble: {
				background: "linear-gradient(135deg, #fd8d16, #da5f7a)",
				padding: "12px 16px",
				borderRadius: "20px 4px 20px 20px",
				boxShadow: "0 2px 12px rgba(218,95,122,0.2)",
				color: "white",
				maxWidth: "520px",
				overflowWrap: "anywhere",
				lineHeight: "1.55",
				fontSize: "0.92rem",
			},
		},
		loading: {
			bubble: { backgroundColor: "transparent" },
		},
	}
};

const DEEP_CHAT_SUBMIT_BUTTON_STYLES = {
	submit: {
		container: { default: { left: "90%" } },
		svg: { styles: { default: { display: "none" } } }
	}
};

const DEEP_CHAT_TEXT_INPUT = {
	styles: {
		text: { display: "none" },
		container: { display: "none" },
	},
};

const DEEP_CHAT_AVATARS = {
	"user": { "src": "", "styles": { "container": { "display": "none" } } },
	"ai": { "src": "/nveil.webp", "styles": { "avatar": { "marginLeft": "-3px", "marginTop": "-5px" } } },
};

// Compute URL/protocol once at module level
const { url: moduleUrl, httpProtocol } = (() => {
	const isLocal = Boolean(import.meta.env.VITE_LOCAL);
	const isTest = Boolean(import.meta.env.VITE_TEST);
	let u, hp;
	if (isLocal) {
		u = import.meta.env.VITE_URL_LOCAL_APP || window.location.host;
		hp = "https";
	} else if (isTest) {
		u = window.location.host;
		hp = "http";
	} else {
		u = window.location.host;
		hp = window.location.protocol === "https:" ? "https" : "http";
	}
	return { url: u, httpProtocol: hp };
})();

const CONNECT_CONFIG = {
	url: `${httpProtocol}://${moduleUrl}/ai/sendUserMessage`,
	method: "POST",
	headers: { "Content-Type": "application/json" },
	credentials: "include",
};

const DEEP_CHAT_ERROR_MESSAGES = { displayServiceErrorMessages: true };
const LOAD_HISTORY_BATCH_SIZE = 20;

// Memoized wrapper: prevents DeepChat from re-rendering when parent re-renders
// with identical props (all module-level constants / useCallback / stable refs).
const StableDeepChat = React.memo(React.forwardRef(function StableDeepChat(props, ref) {
	return <DeepChat ref={ref} {...props} />;
}));

const Chat = ({ roomToken, isRoomReady }) => {
	const { t, i18n } = useTranslation();
	const chatRef = useRef(null);
	const { isAuthenticated, isGuest, secureRequest } = useAuth();
	const { subscribe, subscribeRoom, connected } = useWebSocket();
	const historyRef = useRef(null);
	const [historyStatus, setHistoryStatus] = useState('pending');
	const pendingVizFile = useRef(null);
	const isTrameReady = useRef(false);

	const fileInputRef = useRef(null);
	const welcomeRef = useRef();
	const stageMsgIndexRef = useRef(null);
	const mustOverwrite = useRef(false);
	const chatInputRef = useRef(null);
	const chatResponseTimeoutRef = useRef(null);

	const loadPendingViz = useCallback(() => {
		if (!pendingVizFile.current || !isTrameReady.current) return;
		const vizFile = pendingVizFile.current;
		pendingVizFile.current = null;
		setTimeout(() => {
			window.dispatchEvent(new CustomEvent('loadVizFile', {
				detail: { file: vizFile }
			}));
		}, 800);
	}, []);

	// Reset state on roomToken change (replaces key-based destruction)
	useEffect(() => {
		chatRef.current?.clearMessages?.();
		historyRef.current = null;
		setHistoryStatus('pending');
		stageMsgIndexRef.current = null;
		mustOverwrite.current = false;
		isTrameReady.current = false;
		pendingVizFile.current = null;
		if (chatResponseTimeoutRef.current) {
			clearTimeout(chatResponseTimeoutRef.current);
			chatResponseTimeoutRef.current = null;
		}
	}, [roomToken]);

	// Subscribe to room via WebSocket context (no WS teardown on room switch)
	useEffect(() => {
		if (isAuthenticated && roomToken) {
			subscribeRoom(roomToken);
		}
	}, [isAuthenticated, roomToken, subscribeRoom]);

	// Subscribe to WS events via context
	useEffect(() => {
		if (!isAuthenticated || !roomToken) return;

		const unsubProcessing = subscribe('processing_stage', (data) => {
			const stage = `
			<div style="font-style: normal;color: #ababab;font-size: small;font-weight: 200;">
				${i18n.randomT("chat." + data.stage)}
				<span style="display:inline-block;margin-left:6px;">
				<span style="animation: blink 1s infinite 0s;">.</span>
				<span style="animation: blink 1s infinite 0.2s;">.</span>
				<span style="animation: blink 1s infinite 0.4s;">.</span>
				</span>
			</div>
			`;

			if (mustOverwrite.current === false) {
				stageMsgIndexRef.current = chatRef.current?.addMessage({
					role: "ai",
					html: stage,
					meta: { transient: true, stage: data.stage }
				});
				mustOverwrite.current = true;
			} else {
				chatRef.current?.addMessage({
					role: "ai",
					html: stage,
					meta: { transient: true, stage: data.stage },
					overwrite: true
				});
			}

			if (chatResponseTimeoutRef.current) clearTimeout(chatResponseTimeoutRef.current);
			chatResponseTimeoutRef.current = setTimeout(() => {
				chatRef.current?.addMessage({
					role: "ai",
					html: "<i>Response delayed. Please refresh the page to see the latest messages.</i>",
					overwrite: true
				});
				chatInputRef.current?.setIsWaitingForResponse(false);
				mustOverwrite.current = false;
				chatResponseTimeoutRef.current = null;
			}, 240000);
		});

		const unsubChatResponse = subscribe('chat_response', (data) => {
			if (chatResponseTimeoutRef.current) {
				clearTimeout(chatResponseTimeoutRef.current);
				chatResponseTimeoutRef.current = null;
			}
			const aiText = (data.text || "").replace(/\n/g, "<br>");
			const suggestionsList = data.suggestions || [];
			const selectionPrompt = data.selection_prompt || null;

			let suggestionsHtml = "";
			if (suggestionsList.length > 0) {
				const buttonsHtml = suggestionsList.map(suggItem => {
					const text = typeof suggItem === 'string' ? suggItem : suggItem.text;
					const type = typeof suggItem === 'string' ? 'default' : (suggItem.type || 'default');
					if (type === 'color_palette') {
						const config = suggItem.config ? JSON.stringify(suggItem.config).replace(/"/g, '&quot;') : '{}';
						return `<button class="deep-chat-button deep-chat-suggestion-color-palette" data-palette-config="${config}" onclick="window.dispatchEvent(new CustomEvent('openColorPalette', {detail: JSON.parse(this.dataset.paletteConfig || '{}')}));">${text}</button>`;
					} else if (type === 'show_viz') {
						const config = suggItem.config ? JSON.stringify(suggItem.config).replace(/"/g, '&quot;') : '{}';
						return `<button class="deep-chat-button deep-chat-suggestion-show-viz" data-viz-config="${config}" onclick="window.dispatchEvent(new CustomEvent('loadVizFile', {detail: JSON.parse(this.dataset.vizConfig || '{}')}));">${text}</button>`;
					}
					return '';
				}).filter(Boolean).join('');
				if (buttonsHtml) {
					suggestionsHtml = `<div class="deep-chat-temporary-message">${buttonsHtml}</div>`;
				}
			}

			chatRef.current?.addMessage({
				role: "ai",
				html: aiText + suggestionsHtml,
				overwrite: true
			});

			chatInputRef.current?.setIsWaitingForResponse(false);

			if (selectionPrompt) {
				chatInputRef.current?.setSelectionPrompt(selectionPrompt);
			} else {
				chatInputRef.current?.setSelectionPrompt(null);
			}

			mustOverwrite.current = false;
			setTimeout(() => chatRef.current?.scrollToBottom(), 200);
		});

		const unsubError = subscribe('error', (data) => {
			console.error("Error event:", data.details?.error);
		});

		const unsubDataRefreshed = subscribe('data_refreshed', (data) => {
			queue.add(
				{ title: i18n.t("chat.dataRefreshed") },
				{ timeout: 4000 },
			);
		});

		const unsubSourceDeleted = subscribe('source_deleted', (data) => {
			queue.add(
				{ title: i18n.t("chat.sourceDeletedFromRoom", { fileName: data.file_name || '' }) },
				{ timeout: 8000 },
			);
		});

		return () => {
			unsubProcessing();
			unsubChatResponse();
			unsubError();
			unsubDataRefreshed();
			unsubSourceDeleted();
		};
	}, [isAuthenticated, roomToken, i18n.language, subscribe]);


	useEffect(() => {
		const handleLoadVizFile = async (event) => {
			if (event.detail?.file) {
				performance.mark('viz:build-start');
				try {
					const response = await secureRequest('/viz/send', {
						method: 'POST',
						headers: { 'Content-Type': 'application/json' },
						body: JSON.stringify({
							command: 'build_viz',
							xml_path: event.detail.file
						})
					});
					const resp = response.ok ? await response.json() : null;

					// Deliver widget descriptors from the HTTP response
					if (resp?.widget_descriptors) {
						window.dispatchEvent(new CustomEvent('widget-descriptors', {
							detail: resp.widget_descriptors
						}));
					}

					// Check for missing sources in both error and partial-success cases
					const details = resp?.details || resp?.error || '';
					const missingMatch = details.match(/missing_sources:([^\s]+)/);
					const missingSources = missingMatch ? missingMatch[1].split(',') : [];

					if (missingSources.length > 0) {
						queue.add(
							{
								title: i18n.t('viz.missingDataNamed', { sources: missingSources.join(', ') }),
							},
							{ timeout: 8000 },
						);
					} else if (resp?.status === 'error') {
						queue.add(
							{ title: i18n.t('viz.buildError') },
							{ timeout: 6000 },
						);
					}
				} catch (error) {
					console.error('Error loading viz file:', error);
				}
			}
		};

		window.addEventListener('loadVizFile', handleLoadVizFile);

		return () => {
			window.removeEventListener('loadVizFile', handleLoadVizFile);
		};
	}, []);


	useEffect(() => {
		const controller = new AbortController();

		const fetchUserHistory = async (token) => {
			if (isAuthenticated) {
				try {
					const userHistoryFromDb = await secureRequest('/server/chat/messages', {
						method: 'POST',
						headers: { 'Content-Type': 'application/json' },
						body: JSON.stringify({ nb: 40, room_token: token }),
						signal: controller.signal,
					});
					if (userHistoryFromDb.ok) {
						const data = await userHistoryFromDb.json();
						return data || [];
					}
				}
				catch (error) {
					if (error.name === 'AbortError') return [];
					console.error('Error fetching user history:', error);
					return [];
				}
			}
			return [];
		};

		if (isAuthenticated && roomToken) {
			fetchUserHistory(roomToken).then(userHistory => {
				if (controller.signal.aborted) return;
				if (!userHistory || !Array.isArray(userHistory) || userHistory.length === 0) {
					historyRef.current = [];
					setHistoryStatus('empty');
					if (welcomeRef.current) welcomeRef.current.show();
					return;
				}
				if (welcomeRef.current) welcomeRef.current.hide();
				historyRef.current = userHistory.map(msg => ({
					role: msg.author_email === "bot@nveil.bob" ? "ai" : "user",
					html: msg.content
				}));
				setHistoryStatus('loaded');
				setTimeout(() => {
					chatRef.current?.scrollToBottom();
				}, 100);

				// For guest users, automatically load the last visualization found in history
				if (isGuest && userHistory.length > 0) {
					for (let i = userHistory.length - 1; i >= 0; i--) {
						const msg = userHistory[i];
						if (msg.author_email !== "bot@nveil.bob" || !msg.content) continue;

						// Prefer structured data-viz-config attribute over raw regex
						let vizFile = null;
						try {
							const doc = new DOMParser().parseFromString(msg.content, 'text/html');
							const btn = doc.querySelector('button[data-viz-config]');
							if (btn) {
								const config = JSON.parse(btn.getAttribute('data-viz-config'));
								vizFile = config?.file ?? null;
							}
						} catch { /* malformed HTML or JSON – fall through */ }

						// Fallback: extract filename directly if button parsing failed
						if (!vizFile) {
							const m = msg.content.match(/specificationsEnhanced[\w.-]*\.xml/);
							if (m) vizFile = m[0];
						}

						if (vizFile) {
							pendingVizFile.current = vizFile;
							loadPendingViz();
							break;
						}
					}
				}
			});
		}
		else if (!isAuthenticated) {
			historyRef.current = [];
			setHistoryStatus('empty');
			if (window.location.pathname == '/') {
				if (welcomeRef.current) welcomeRef.current.show();
			}
		}

		return () => controller.abort();
	}, [isAuthenticated, roomToken, isGuest]);

	useEffect(() => {
		const onTrameReady = (e) => {
			isTrameReady.current = true;
			setTimeout(() => chatRef.current.scrollToBottom(), 1100);
			loadPendingViz();
		};

		window.addEventListener('trame-ready', onTrameReady);
		return () => window.removeEventListener('trame-ready', onTrameReady);
	}, [loadPendingViz]);

	// Memoize DeepChat callback props
	const onComponentRender = useCallback(() => {
		if (!chatRef.current) return;
		setTimeout(() => {
			chatRef.current?.scrollToBottom();
		}, 200);
	}, []);

	const languageRef = useRef(i18n.language);
	useEffect(() => {
		languageRef.current = i18n.language;
	}, [i18n.language]);

	const requestInterceptor = useCallback((details) => {
		stageMsgIndexRef.current = null;
		if (chatResponseTimeoutRef.current) {
			clearTimeout(chatResponseTimeoutRef.current);
			chatResponseTimeoutRef.current = null;
		}

		if (welcomeRef.current) welcomeRef.current.hide();
		chatInputRef.current?.setIsWaitingForResponse(true);
		trackEvent("chat_message_sent");
		if (details.body) {
			details.body.user_language = languageRef.current;
		}
		return details;
	}, []);

	const responseInterceptor = useCallback((response) => {
		// Async mode: server returned immediately, real response comes via WebSocket
		if (response?.async) {
			mustOverwrite.current = true;
			return {
				role: "ai",
				html: `<div style="font-style:normal;color:#ababab;font-size:small;font-weight:200;">
					<span style="display:inline-block;">
						<span style="animation:blink 1s infinite 0s;">.</span>
						<span style="animation:blink 1s infinite 0.2s;">.</span>
						<span style="animation:blink 1s infinite 0.4s;">.</span>
					</span>
				</div>`
			};
		}

		const removeScript = "this.parentElement.remove()";
		const suggestionsList = response.suggestions || [];
		const aiText = response.text || response.html || "";
		let suggestionsHtml = "";

		if (suggestionsList.length > 0) {
			const buttonsHtml = suggestionsList.map(suggItem => {
				const text = typeof suggItem === 'string' ? suggItem : suggItem.text;
				const type = typeof suggItem === 'string' ? 'default' : (suggItem.type || 'default');

				let additionalClass = "";
				if (type === 'positive' || type === 'closed_yes') {
					additionalClass = "deep-chat-suggestion-positive";
				} else if (type === 'negative' || type === 'closed_no') {
					additionalClass = "deep-chat-suggestion-negative";
				} else if (type === 'color_palette') {
					additionalClass = "deep-chat-suggestion-color-palette";
					const config = suggItem.config ? JSON.stringify(suggItem.config).replace(/"/g, '&quot;') : '{}';
					return `<button class="deep-chat-button ${additionalClass}"
					data-palette-config="${config}"
					onclick="window.dispatchEvent(new CustomEvent('openColorPalette', {detail: JSON.parse(this.dataset.paletteConfig || '{}')}));">${text}</button>`;
				} else if (type === 'show_viz') {
					additionalClass = "deep-chat-suggestion-show-viz";
					const config = suggItem.config ? JSON.stringify(suggItem.config).replace(/"/g, '&quot;') : '{}';
					return `<button class="deep-chat-button ${additionalClass}"
					data-viz-config="${config}"
					onclick="window.dispatchEvent(new CustomEvent('loadVizFile', {detail: JSON.parse(this.dataset.vizConfig || '{}')}));">${text}</button>`;
				}

				return `<button class="deep-chat-button deep-chat-suggestion-button ${additionalClass}" onclick="${removeScript}">${text}</button>`;
			}).join('');

			suggestionsHtml = `<div class="deep-chat-temporary-message">${buttonsHtml}</div>`;
		}

		const finalBubble = {
			role: "ai",
			html: aiText + suggestionsHtml,
			overwrite: true
		};

		chatInputRef.current?.setIsWaitingForResponse(false);

		setTimeout(() => {
			chatRef.current?.scrollToBottom();
		}, 200);

		mustOverwrite.current = false;
		return finalBubble;
	}, []);

	const loadHistory = useCallback(async (index) => {
		if (!isAuthenticated || isGuest || !roomToken) return [];
		// Deep Chat fires loadHistory(0) on mount; the `history` prop already
		// displays the first 40 messages, so skip — but return [false] so the
		// trailing-falsy sentinel keeps scroll-to-top pagination enabled.
		// First real scroll-to-top call is index=2 (setupInitialHistory bumps _index).
		if (index < 2) return [false];
		const offset = 40 + (index - 2) * LOAD_HISTORY_BATCH_SIZE;
		try {
			const response = await secureRequest('/server/chat/messages', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					nb: LOAD_HISTORY_BATCH_SIZE,
					offset,
					room_token: roomToken,
				}),
			});
			if (!response.ok) return [];
			const data = await response.json();
			if (!Array.isArray(data) || data.length === 0) return [];
			const mapped = data.map(msg => ({
				role: msg.author_email === 'bot@nveil.bob' ? 'ai' : 'user',
				html: msg.content,
			}));
			// Append `false` sentinel when the batch is full — signals "more pages exist".
			return data.length === LOAD_HISTORY_BATCH_SIZE ? [...mapped, false] : mapped;
		} catch (error) {
			console.error('Error loading history page:', error);
			return [];
		}
	}, [isAuthenticated, isGuest, roomToken, secureRequest]);

	return (
		<div className={styles.chatContainer}>
			<WelcomeMessage ref={welcomeRef} i18n={i18n} styles={styles} isAuthenticated={isAuthenticated} />

			<div className={styles.deepChatWrapper}>
			{historyStatus !== 'pending' && (
				<StableDeepChat
					ref={chatRef}
					history={historyRef.current}
					loadHistory={loadHistory}
					connect={CONNECT_CONFIG}
					errorMessages={DEEP_CHAT_ERROR_MESSAGES}
					avatars={DEEP_CHAT_AVATARS}
					style={DEEP_CHAT_STYLE}
					auxiliaryStyle={deepChatStyles}
					submitButtonStyles={DEEP_CHAT_SUBMIT_BUTTON_STYLES}
					textInput={DEEP_CHAT_TEXT_INPUT}
					chatStyle={DEEP_CHAT_CHAT_STYLE}
					displayLoadingBubble={true}
					messageStyles={DEEP_CHAT_MESSAGE_STYLES}
					onComponentRender={onComponentRender}
					requestInterceptor={requestInterceptor}
					responseInterceptor={responseInterceptor}
				/>
			)}
			</div>

			<CustomInput
				ref={chatInputRef}
				isAuthenticated={isAuthenticated}
				isGuest={isGuest}
				isRoomReady={isRoomReady}
				fileInputRef={fileInputRef}
				t={t}
				chatRef={chatRef}
				wsConnection={connected}
			/>

			<PaletteModal
				chatRef={chatRef}
				onPaletteSaved={(name) => chatInputRef.current?.insertPaletteTag(name)}
			/>
		</div>
	);
};

export default React.memo(Chat);
