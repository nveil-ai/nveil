// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-FileContributor: Guillaume Franque
// SPDX-FileContributor: Clément Baraille
// SPDX-License-Identifier: AGPL-3.0-or-later

import styles from "./Chat.module.css";
import React, { useRef, useEffect, useState, useMemo, useImperativeHandle, useCallback } from 'react';
import { buildIsoDuration } from '../Components/SequenceOptions';
import { queue } from '../App';
import { TbFileTypeCsv } from "react-icons/tb";
import { TbFileTypeXls } from "react-icons/tb";
import { FaFileMedical } from "react-icons/fa";
import { PiPaperPlaneRightFill } from "react-icons/pi";
import { BsPaperclip } from "react-icons/bs";
import { HiStop } from "react-icons/hi";
import { FaFile } from "react-icons/fa";
import Select from 'react-select';
import { mergeSelectStyles, darkSelectTheme } from "../utils/selectStyles";
import PaletteMenu from "../Components/Palette/PaletteMenu";
import VariablePickerModal from "../Components/VariablePickerModal";
import DataSourcesModal from "../Components/DataSourcesModal";
import SelectionPrompt from "./SelectionPrompt";
import { useRoom } from "../Room/RoomContext";
import { useAuth } from "../Auth/AuthContext";
import useAllowedExtensions from "../hooks/useAllowedExtensions";
import { hasBilling } from '../extensions';

const maxSize = 1000 * 1024 * 1024; // 10000MB

// Helper to pick icon based on extension
const getFileIcon = (file) => {
	const ext = file.name.toLowerCase().substring(file.name.lastIndexOf('.'));
	if (ext === ".csv") return <TbFileTypeCsv style={{ fontSize: '1.2em', color: "#ffffffff" }} />;
	if (ext === ".xlsx" || ext === ".xls"|| ext === ".ods"|| ext === ".xlsm") return <TbFileTypeXls style={{ fontSize: '1.2em', color: "#22c55e" }} />;
	if (ext === ".mhd" || ext === ".zraw") return <FaFileMedical style={{ fontSize: '1.2em', color: "#ffffffff" }} />;
	return <FaFile style={{ fontSize: '1.2em', color: "#6859a3" }} />;
};

/**
 * Simple sanitizer for contentEditable HTML.
 * Allows only specific safe spans and basic formatting.
 */
const sanitizeHTML = (html) => {
    if (!html) return "";
    const doc = new DOMParser().parseFromString(html, "text/html");
    const allowedTags = ["SPAN", "BR"];
    const allowedClasses = [
        "highlighted_word",
        "hw_table",
        "hw_dot",
        "hw_field",
        "palette-tag",
    ];

    const clean = (node) => {
        if (node.nodeType === 3) return; // Text node
        if (node.nodeType !== 1) {
            node.remove();
            return;
        }

        if (!allowedTags.includes(node.tagName)) {
            const text = node.textContent;
            node.replaceWith(document.createTextNode(text));
            return;
        }

        // Strip all attributes except specific safe ones
        const attrs = Array.from(node.attributes);
        for (const attr of attrs) {
            const name = attr.name.toLowerCase();
            if (name.startsWith("on") || name === "id" || (name === "style" && !node.classList.contains("palette-tag"))) {
                node.removeAttribute(attr.name);
            }
        }

        if (node.tagName === "SPAN") {
            const classes = Array.from(node.classList);
            for (const cls of classes) {
                if (!allowedClasses.includes(cls)) {
                    node.classList.remove(cls);
                }
            }
            if (node.classList.contains("highlighted_word")) {
                node.setAttribute("contenteditable", "false");
            }
        }

        Array.from(node.childNodes).forEach(clean);
    };

    Array.from(doc.body.childNodes).forEach(clean);
    return doc.body.innerHTML;
};

function FilePills({ files, onClick }) {
    const containerRef = useRef(null);
    const measureRef = useRef(null);
    const [visibleCount, setVisibleCount] = useState(files.length);

    useEffect(() => {
        const container = containerRef.current;
        const measureEl = measureRef.current;
        if (!container || !measureEl || files.length === 0) {
            setVisibleCount(files.length);
            return;
        }

        const measure = () => {
            const containerWidth = container.getBoundingClientRect().width;
            const pills = Array.from(measureEl.children);
            if (pills.length === 0) return;

            const gap = 4;
            const overflowPillWidth = 40;
            let usedWidth = 0;
            let count = 0;

            for (let i = 0; i < pills.length; i++) {
                const pillWidth = pills[i].getBoundingClientRect().width;
                const nextWidth = usedWidth + (count > 0 ? gap : 0) + pillWidth;
                const isLast = i === pills.length - 1;

                if (isLast) {
                    // last pill: just needs to fit
                    if (nextWidth <= containerWidth) { count++; }
                } else {
                    // not last: needs room for itself + gap + overflow pill
                    if (nextWidth + gap + overflowPillWidth <= containerWidth) {
                        count++;
                        usedWidth = nextWidth;
                    } else {
                        break;
                    }
                }
            }
            setVisibleCount(Math.max(1, count));
        };

        measure();
        const observer = new ResizeObserver(measure);
        observer.observe(container);
        return () => observer.disconnect();
    }, [files]);

    const hiddenFiles = files.slice(visibleCount);
    const hiddenTooltip = hiddenFiles.map(f => f.display_name || f.original_name).join('\n');

    return (
        <div ref={containerRef} className={styles.filePillsContainer}>
            {/* Hidden measurement row — all pills rendered offscreen */}
            <div ref={measureRef} className={styles.filePillsMeasure} aria-hidden="true">
                {files.map(f => (
                    <span key={f.id} className={styles.filePill}>
                        {f.display_name || f.original_name}
                    </span>
                ))}
            </div>
            {files.slice(0, visibleCount).map(f => (
                <span
                    key={f.id}
                    className={styles.filePill}
                    data-tooltip={f.display_name || f.original_name}
                    onClick={onClick}
                >
                    {f.display_name || f.original_name}
                </span>
            ))}
            {hiddenFiles.length > 0 && (
                <span
                    className={styles.filePill}
                    data-tooltip={hiddenTooltip}
                    onClick={onClick}
                >
                    (+{hiddenFiles.length})
                </span>
            )}
        </div>
    );
}

const CustomInput = React.memo(React.forwardRef(function CustomInput(
    { isAuthenticated, isGuest, isRoomReady, fileInputRef, t, chatRef, wsConnection },
    ref
) {
    const { extensions: allowedExtensions, accept: allowedAccept } = useAllowedExtensions();
    const [currentMessage, setCurrentMessage] = useState('');
    const [historyIndex, setHistoryIndex] = useState(-1);
    const [tempMessage, setTempMessage] = useState('');
    const customInputRef = useRef(null);
    const uploadProgressRef = useRef(null);
    const [userMessageHistory, setUserMessageHistory] = useState([]);
    const [fields, setFields] = useState([]);
    const [dataIdToFilename, setDataIdToFilename] = useState({});
    const [catalogueStats, setCatalogueStats] = useState(null);
    const [pendingFiles, setPendingFiles] = useState([]);
    const [isDragActive, setIsDragActive] = useState(false);
    const [isUploading, setIsUploading] = useState(false);
    const [filesStatus, setFilesStatus] = useState(t("chat.uploadReady"));
    const [isSingleLine, setIsSingleLine] = useState(true);
    const [isWaitingForResponse, setIsWaitingForResponse] = useState(false);
    const [isVariablePickerOpen, setIsVariablePickerOpen] = useState(false);
    const [variablePickerFilter, setVariablePickerFilter] = useState('');
    const [uploadError, setUploadError] = useState(null);
    const [selectionPrompt, setSelectionPrompt] = useState(null);
    const [selectionFocusIndex, setSelectionFocusIndex] = useState(0);
    const savedRangeRef = useRef(null);
    const isVariablePickerOpenRef = useRef(false);
    const isInputEnabled = isAuthenticated && isRoomReady;
	const [isDataSourcesOpen, setIsDataSourcesOpen] = useState(false);
	const isDataSourcesOpenRef = useRef(false);
	useEffect(() => { isDataSourcesOpenRef.current = isDataSourcesOpen; }, [isDataSourcesOpen]);

	const { currentRoom } = useRoom();
	const { setShowAuthModal, secureRequest } = useAuth();

	// URL source state
	const [isUrlLoading, setIsUrlLoading] = useState(false);
	const [hasUrlSources, setHasUrlSources] = useState(false);
	const [refreshInterval, setRefreshInterval] = useState(null);
	const [isRefreshing, setIsRefreshing] = useState(false);

    useImperativeHandle(ref, () => ({
        setIsWaitingForResponse: (v) => setIsWaitingForResponse(v),
        isWaitingForResponse: () => isWaitingForResponse,
        insertPaletteTag: (name) => insertPaletteTag(name),
        setSelectionPrompt: (prompt) => {
            setSelectionPrompt(prompt);
            setSelectionFocusIndex(0);
        },
    }));

    // Build datasets array for the modal — prefer catalogue_stats (rich metadata) over fields
    const datasets = useMemo(() => {
        if (catalogueStats && Object.keys(catalogueStats).length > 0) {
            return Object.entries(catalogueStats).map(([name, ds]) => ({
                data_id: name,
                name,
                row_count: ds.row_count,
                fields: (ds.fields || []).map(f => ({
                    name: f.name,
                    data_type: f.data_type,
                    min_value: f.min_value,
                    max_value: f.max_value,
                    is_unique: f.is_unique,
                    distinct_count: f.distinct_count,
                    uniques: f.uniques,
                })),
            }));
        }
        const grouped = {};
        for (const field of fields) {
            const dataId = field.data_id || "Unknown";
            if (!grouped[dataId]) {
                grouped[dataId] = {
                    data_id: dataId,
                    name: dataIdToFilename[dataId] || `Dataset ${dataId}`,
                    fields: []
                };
            }
            grouped[dataId].fields.push({ name: field.field_name });
        }
        return Object.values(grouped);
    }, [catalogueStats, fields, dataIdToFilename]);

    // Upload files to data store only — returns file IDs (no linking)
    const uploadFilesToStore = (files, connector = null, sequenceMeta = null) => {
        return new Promise((resolve, reject) => {
            const form = new FormData();
            setIsUploading(true);
            setUploadError(null);
            setFilesStatus(t("chat.uploading"));
            const validFiles = Array.from(files).filter(file => {
                const ext = file.name.toLowerCase().substring(file.name.lastIndexOf('.'));
                return (
                    allowedExtensions.includes(ext) &&
                    file.size <= maxSize
                );
            });

            if (validFiles.length === 0) {
                alert(t("chat.upload.invalidFile"));
                setIsUploading(false);
                setFilesStatus(t("chat.uploadReady"));
                reject(new Error("Invalid file"));
                return;
            }

            for (const file of validFiles) form.append("files", file, file.name);
            if (connector) form.append("connector", connector);
            if (sequenceMeta) {
                form.append("sequence_time_mode", sequenceMeta.timeMode);
                if (sequenceMeta.timeMode === "time_based") {
                    form.append("sequence_time_delta", buildIsoDuration(sequenceMeta.timeMode, sequenceMeta.deltaValue, sequenceMeta.deltaUnit));
                }
            }

            const xhr = new XMLHttpRequest();
            xhr.open("POST", "/server/data/upload", true);

            xhr.upload.onprogress = function (e) {
                if (uploadProgressRef.current && e.lengthComputable) {
                    const percent = Math.round((e.loaded / e.total) * 100);
                    uploadProgressRef.current.value = percent;
                }
            };

            xhr.onload = function () {
                if (uploadProgressRef.current) uploadProgressRef.current.value = 0;

                if (xhr.status === 200) {
                    let uploadData;
                    try {
                        uploadData = JSON.parse(xhr.responseText);
                    } catch (e) {
                        setIsUploading(false);
                        setFilesStatus(t("chat.uploadReady"));
                        reject(new Error("Invalid upload response"));
                        return;
                    }

                    const fileIds = (uploadData.files || []).map(f => f.id);
                    setIsUploading(false);
                    setFilesStatus(t("chat.uploadReady"));
                    resolve(fileIds);
                } else if (xhr.status === 413) {
                    let errorMessage = t("chat.fileTooLarge");
                    try {
                        const response = JSON.parse(xhr.responseText);
                        if (response.detail) errorMessage = response.detail;
                    } catch (e) { /* default */ }
                    setUploadError(errorMessage);
                    setIsUploading(false);
                    setFilesStatus(t("chat.uploadReady"));
                    setPendingFiles([]);
                    reject(new Error(errorMessage));
                } else if (xhr.status === 409) {
                    let errorMessage = t("chat.upload.duplicate");
                    try {
                        const response = JSON.parse(xhr.responseText);
                        if (response.detail) errorMessage = response.detail;
                    } catch (e) { /* default */ }
                    setUploadError(errorMessage);
                    setIsUploading(false);
                    setFilesStatus(t("chat.uploadReady"));
                    reject(new Error(errorMessage));
                } else if (xhr.status === 403) {
                    let errorMessage = t("chat.uploadNotAllowed");
                    try {
                        const response = JSON.parse(xhr.responseText);
                        if (response.detail) errorMessage = response.detail;
                    } catch (e) { /* default */ }
                    setUploadError(errorMessage);
                    setIsUploading(false);
                    setFilesStatus(t("chat.uploadReady"));
                    setPendingFiles([]);
                    reject(new Error(errorMessage));
                } else {
                    setUploadError(t("chat.upload.failed"));
                    setIsUploading(false);
                    setFilesStatus(t("chat.uploadReady"));
                    reject(new Error(xhr.statusText));
                }
            };

            xhr.onerror = function () {
                if (uploadProgressRef.current) uploadProgressRef.current.value = 0;
                setUploadError(t("chat.upload.failed"));
                setIsUploading(false);
                setFilesStatus(t("chat.uploadReady"));
                reject(new Error("Upload failed"));
            };

			xhr.send(form);
		});
	};

	// Batch apply link/unlink changes to room
	const applyFileChanges = async (linkFileIds, unlinkFileIds) => {
		const roomId = currentRoom?.id;
		if (!roomId) throw new Error("No active room");
		if (linkFileIds.length === 0 && unlinkFileIds.length === 0) return;

		const resp = await fetch(`/server/rooms/${roomId}/apply-files`, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({
				link_file_ids: linkFileIds,
				unlink_file_ids: unlinkFileIds,
			}),
			credentials: "include",
		});
		if (!resp.ok) throw new Error("Failed to apply file changes");
		const data = await resp.json();
		if (data.status !== "ok") throw new Error("Apply error");

		// Refresh catalogue stats after apply
		try {
			const statsResp = await fetch("/server/files/get_catalogue_stats?type=input", { credentials: "include" });
			if (statsResp.ok) {
				const stats = await statsResp.json();
				if (stats?.datasets && Object.keys(stats.datasets).length > 0) {
					setCatalogueStats(stats.datasets);
				}
			}
		} catch (_) { /* silent */ }

		// Refresh user files (updates pills + modal data)
		fetchUserFiles();

		// Warn if all sources were removed
		if (data.no_sources_remaining) {
			queue.add(
				{ title: t("chat.noSourcesRemaining") },
				{ timeout: 8000 },
			);
		}

		// Chat feedback
		if (chatRef.current) {
			const parts = [];
			const linkedNames = data.linked_names || [];
			const unlinkedNames = data.unlinked_names || [];
			if (linkedNames.length > 0) {
				parts.push(t("chat.sourceAdded", { count: linkedNames.length, names: linkedNames.join(', ') }));
			}
			if (unlinkedNames.length > 0) {
				parts.push(t("chat.sourceRemoved", { count: unlinkedNames.length, names: unlinkedNames.join(', ') }));
			}

			if (parts.length > 0) {
				const messageText = parts.join('. ');
				chatRef.current.submitUserMessage({
					text: messageText,
					html: `<span>${messageText}</span>`,
					custom: { upload: true },
				});
			}
		}
	};



	// Upload URL to data store only — returns file IDs (no linking)
	const uploadUrlToStore = async (url, label) => {
		if (!url) return [];

		setIsUrlLoading(true);
		setFilesStatus(t("chat.urlProcessing"));
		try {
			const uploadResp = await fetch("/server/data/upload-url", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ urls: [{ url, label: label || "", format: "AUTO" }] }),
				credentials: "include",
			});
			if (!uploadResp.ok) throw new Error("URL upload failed");
			const uploadData = await uploadResp.json();

			const fileIds = (uploadData.files || []).map(f => f.id);
			return fileIds;
		} catch (err) {
			console.error("URL upload error:", err);
			return [];
		} finally {
			setIsUrlLoading(false);
			setFilesStatus(t("chat.uploadReady"));
		}
	};

	const handleRefreshUrlSources = async () => {
		setIsRefreshing(true);
		try {
			await fetch("/viz/refresh_url_sources", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({}),
				credentials: "include",
			});
		} catch (err) {
			console.error("Refresh error:", err);
		} finally {
			setIsRefreshing(false);
		}
	};

	const handleSetRefreshInterval = async (seconds) => {
		setRefreshInterval(seconds);
		try {
			await fetch("/viz/set_refresh_interval", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ interval: seconds || 0 }),
				credentials: "include",
			});
		} catch (err) {
			console.error("Set refresh interval error:", err);
		}
	};

	// Cancel auto-refresh on unmount (leaving the room)
	useEffect(() => {
		return () => {
			fetch("/viz/set_refresh_interval", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ interval: 0 }),
				credentials: "include",
			}).catch(() => {});
		};
	}, []);

	// Check for existing URL sources on mount
	useEffect(() => {
		if (!isAuthenticated || !wsConnection) return;
		fetch("/server/files/get_metadata?metadata_name=url_sources", { credentials: "include" })
			.then(r => r.ok ? r.json() : {})
			.then(data => {
				if (data?.url_sources && data.url_sources.length > 0) {
					setHasUrlSources(true);
				}
			})
			.catch(() => {});
	}, [isAuthenticated, wsConnection]);

	// Fetch user files (shared with DataSourcesModal — single source of truth)
	const [userFiles, setUserFiles] = useState([]);
	const fetchUserFiles = useCallback(async () => {
		try {
			const res = await secureRequest('/server/data/list');
			if (res.ok) {
				const data = await res.json();
				setUserFiles(data.files || []);
			}
		} catch (_) { /* silent */ }
	}, [secureRequest]);

	useEffect(() => {
		if (!isAuthenticated || !wsConnection || !currentRoom) return;
		fetchUserFiles();
	}, [isAuthenticated, wsConnection, currentRoom, fetchUserFiles]);

	// Derive linked files for pills from userFiles
	const linkedFiles = useMemo(() => {
		const roomId = currentRoom?.id;
		if (!roomId) return [];
		return userFiles.filter(f => (f.linked_room_ids || []).includes(roomId));
	}, [userFiles, currentRoom]);

    useEffect(() => {
        if (!isAuthenticated) {
            setUserMessageHistory([]);
        }
    }, [isAuthenticated, wsConnection]);

    useEffect(() => {
        if (!isAuthenticated || !wsConnection) return;

        // Clear stale metadata from previous room
        setFields([]);
        setDataIdToFilename({});
        setCatalogueStats(null);

        // Fetch datasets metadata
        fetch("/server/files/get_metadata?metadata_name=datasets", {
            method: "GET",
            credentials: "include",
        })
            .then(response => {
                if (!response.ok) throw new Error("Failed to fetch datasets");
                return response.json();
            })
            .then(data => {
                if (data.datasets && data.datasets.length > 0) {
                    const fieldsList = [];
                    const filenameMap = {};
                    data.datasets.forEach(dataset => {
                        if (dataset.name) {
                            filenameMap[dataset.data_id] = dataset.name;
                        }
                        (dataset.fields || []).forEach(field => {
                            fieldsList.push({
                                data_id: dataset.data_id,
                                field_name: field.name
                            });
                        });
                    });
                    setFields(fieldsList);
                    setDataIdToFilename(filenameMap);
                }
            })
            .catch(err => {
                console.error("Error fetching datasets :", err);
            });

        // Fetch catalogue stats (rich field metadata for variable picker)
        fetch("/server/files/get_catalogue_stats?type=input", {
            method: "GET",
            credentials: "include",
        })
            .then(response => {
                if (!response.ok) throw new Error("Failed to fetch catalogue stats");
                return response.json();
            })
            .then(data => {
                if (data.datasets && Object.keys(data.datasets).length > 0) {
                    setCatalogueStats(data.datasets);
                }
            })
            .catch(err => {
                console.error("Error fetching catalogue stats:", err);
            });
    }, [isAuthenticated, wsConnection, currentRoom]);

    // Imperatively set contentEditable
    useEffect(() => {
        if (!customInputRef.current) return;
        customInputRef.current.contentEditable = (isInputEnabled && !isGuest) ? "true" : "false";
        if (isInputEnabled && !isGuest) {
            customInputRef.current.focus();
        }
    }, [isInputEnabled, isAuthenticated, isGuest]);

    // Robust helper: focus element and place caret at end (works with empty nodes)
    const focusAndPlaceCaretAtEnd = (el) => {
        if (!el) return;
        try {
            if (typeof el.focus === 'function') el.focus();
            let node = el;
            while (node && node.lastChild && node.lastChild.nodeType === Node.ELEMENT_NODE) {
                node = node.lastChild;
            }
            if (!node.lastChild || node.lastChild.nodeType !== Node.TEXT_NODE) {
                const text = document.createTextNode('');
                node.appendChild(text);
            }
            const textNode = node.lastChild;
            const offset = textNode.textContent.length;
            const range = document.createRange();
            range.setStart(textNode, offset);
            range.collapse(true);
            const sel = window.getSelection ? window.getSelection() : document.selection;
            sel.removeAllRanges();
            sel.addRange(range);
        } catch (err) {
            // ignore selection errors silently
        }
    };

    // Timed refocus attempts to reliably override DeepChat's own refocus (which uses setTimeout(0)).
    const refocusTimersRef = useRef([]);
    const scheduleRefocus = () => {
        (refocusTimersRef.current || []).forEach(id => clearTimeout(id));
        refocusTimersRef.current = [];

        const tryRefocus = () => {
            if (!customInputRef.current) return;
            if (isVariablePickerOpenRef.current) return;
            try {
                customInputRef.current.focus();
                focusAndPlaceCaretAtEnd(customInputRef.current);
            } catch (err) { /* ignore */ }
        };

        tryRefocus();
        requestAnimationFrame(tryRefocus);
        refocusTimersRef.current.push(setTimeout(tryRefocus, 0));
        refocusTimersRef.current.push(setTimeout(tryRefocus, 50));
        refocusTimersRef.current.push(setTimeout(tryRefocus, 150));
    };
    
    const handlePaste = (e) => {
        if (isVariablePickerOpenRef.current) return;
        e.preventDefault();
        const text = e.clipboardData.getData('text/plain');
        document.execCommand('insertText', false, text);
    };

    // If DeepChat (or other components) steals focus, intercept focusin and redirect back to our input
    useEffect(() => {
        const onFocusIn = (e) => {
            if (!customInputRef.current) return;
            const target = e.target;
            if (target === customInputRef.current) return;

            let deepHost = null;
            try {
                deepHost = chatRef.current?.shadowRoot || document.querySelector('deep-chat')?.shadowRoot || document.querySelector('deep-chat');
            } catch (err) { deepHost = null; }
            if (!deepHost) return;
            const contains = (node, targetNode) => {
                if (!node || !targetNode) return false;
                if (node.contains) return node.contains(targetNode);
                let cur = targetNode;
                while (cur) {
                    if (cur === node) return true;
                    cur = cur.parentNode || cur.host;
                }
                return false;
            };
            if (contains(deepHost, target)) {
                scheduleRefocus();
            }
        };
        document.addEventListener('focusin', onFocusIn, true);
        return () => {
            document.removeEventListener('focusin', onFocusIn, true);
            (refocusTimersRef.current || []).forEach(id => clearTimeout(id));
            refocusTimersRef.current = [];
        };
    }, []);

    useEffect(() => {
        const handleDragOver = (e) => {
            e.preventDefault();
            if (isDataSourcesOpenRef.current) return; // modal handles its own drops
            if (e.dataTransfer.types.includes('Files')) {
                setIsDragActive(true);
            }
        };
        const handleDragLeave = (e) => {
            if (
                e.pageX <= 0 ||
                e.pageY <= 0 ||
                e.pageX >= window.innerWidth ||
                e.pageY >= window.innerHeight
            ) {
                setIsDragActive(false);
            }
        };
        if (isInputEnabled && !isGuest) {
            document.addEventListener('dragover', handleDragOver);
            document.addEventListener('dragleave', handleDragLeave);
        }
        return () => {
            document.removeEventListener('dragover', handleDragOver);
            document.removeEventListener('dragleave', handleDragLeave);
        };
    }, [isInputEnabled]);

    const handleKeyDown = (e) => {
        if (!isInputEnabled || isGuest) return;
        function setCaretToEnd(el) {
            const range = document.createRange();
            range.selectNodeContents(el);
            range.collapse(false);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
        }

        // Intercept @ to open variable picker modal
        if (e.key === '@' && datasets.length > 0) {
            e.preventDefault();
            const sel = window.getSelection();
            if (sel && sel.rangeCount > 0) {
                savedRangeRef.current = sel.getRangeAt(0).cloneRange();
            }
            isVariablePickerOpenRef.current = true;
            setVariablePickerFilter('');
            setIsVariablePickerOpen(true);
            return;
        }

        // Selection prompt keyboard navigation
        // options indices 0..length-1 are the radio cards, index === length is "Other" (free text)
        if (selectionPrompt) {
            const otherIndex = selectionPrompt.options.length;
            if (e.key === 'ArrowUp') {
                e.preventDefault();
                setSelectionFocusIndex(prev => (prev > 0 ? prev - 1 : otherIndex));
                return;
            }
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                setSelectionFocusIndex(prev => (prev < otherIndex ? prev + 1 : 0));
                return;
            }
            if (e.key === 'Enter' && !e.shiftKey) {
                if (selectionFocusIndex < otherIndex) {
                    e.preventDefault();
                    handleSelectionSubmit(selectionPrompt.options[selectionFocusIndex]);
                    return;
                }
                // "Other" is focused — fall through to normal Enter handling
            }
            if (e.key === 'Escape') {
                e.preventDefault();
                setSelectionPrompt(null);
                setSelectionFocusIndex(0);
                return;
            }
            // Any printable key while on a radio option → auto-switch to "Other"
            if (selectionFocusIndex < otherIndex && e.key.length === 1 && !e.ctrlKey && !e.metaKey) {
                setSelectionFocusIndex(otherIndex);
            }
            // Fall through to normal input
        }

        if (customInputRef.current) {
            if (e.key === 'ArrowUp') {
                e.preventDefault();

                if (userMessageHistory.length === 0) return;

                if (historyIndex === -1) {
                    setTempMessage(currentMessage);
                    setHistoryIndex(userMessageHistory.length - 1);
                    const safeHtml = sanitizeHTML(userMessageHistory[userMessageHistory.length - 1]);
                    customInputRef.current.innerHTML = safeHtml;
                    setCurrentMessage(safeHtml);
                } else if (historyIndex > 0) {
                    setHistoryIndex(historyIndex - 1);
                    const safeHtml = sanitizeHTML(userMessageHistory[historyIndex - 1]);
                    customInputRef.current.innerHTML = safeHtml;
                    setCurrentMessage(safeHtml);
                }
                setCaretToEnd(customInputRef.current);
            } else if (e.key === 'ArrowDown') {
                e.preventDefault();
                if (historyIndex === -1) return;

                if (historyIndex < userMessageHistory.length - 1) {
                    setHistoryIndex(historyIndex + 1);
                    const safeHtml = sanitizeHTML(userMessageHistory[historyIndex + 1]);
                    customInputRef.current.innerHTML = safeHtml;
                    setCurrentMessage(safeHtml);
                } else {
                    setHistoryIndex(-1);
                    const safeHtml = sanitizeHTML(tempMessage);
                    customInputRef.current.innerHTML = safeHtml;
                    setCurrentMessage(safeHtml);
                    setTempMessage('');
                }
                setCaretToEnd(customInputRef.current);
            } else if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (isWaitingForResponse) return;
                handleSendMessage(currentMessage.trim());
                setCurrentMessage('');
                setHistoryIndex(-1);
                setTempMessage('');
                if (customInputRef.current) customInputRef.current.textContent = '';
				setIsSingleLine(true);
                scheduleRefocus();
            }

        }
    };

    const insertVariable = useCallback(({ datasetName, fieldName }) => {
        if (!customInputRef.current) return;

        customInputRef.current.focus();
        const sel = window.getSelection();

        // Restore saved caret position from before the modal opened
        if (savedRangeRef.current) {
            sel.removeAllRanges();
            sel.addRange(savedRangeRef.current);
            savedRangeRef.current = null;
        } else if (!sel || sel.rangeCount === 0 || !customInputRef.current.contains(sel.anchorNode)) {
            focusAndPlaceCaretAtEnd(customInputRef.current);
        }

        const singleTable = datasets.length === 1;
        const fullText = singleTable ? fieldName : `${datasetName}.${fieldName}`;

        const range = sel.getRangeAt(0);
        range.deleteContents();
        const span = document.createElement('span');
        span.className = 'highlighted_word';
        span.contentEditable = 'false';
        span.title = fullText;

        if (singleTable) {
            const fieldSpan = document.createElement('span');
            fieldSpan.className = 'hw_field';
            fieldSpan.textContent = fieldName;
            span.appendChild(fieldSpan);
        } else {
            const tableSpan = document.createElement('span');
            tableSpan.className = 'hw_table';
            tableSpan.textContent = datasetName;
            const dot = document.createElement('span');
            dot.className = 'hw_dot';
            dot.textContent = '.';
            const fieldSpan = document.createElement('span');
            fieldSpan.className = 'hw_field';
            fieldSpan.textContent = fieldName;
            span.appendChild(tableSpan);
            span.appendChild(dot);
            span.appendChild(fieldSpan);
        }

        const spacer = document.createTextNode('\u00A0');
        range.insertNode(spacer);
        range.insertNode(span);
        range.setStartAfter(spacer);
        range.collapse(true);
        sel.removeAllRanges();
        sel.addRange(range);
        setCurrentMessage(customInputRef.current.innerHTML);
        scheduleRefocus();
    }, [datasets.length]);

    const handleSelectionSubmit = useCallback((option) => {
        setSelectionPrompt(null);
        setSelectionFocusIndex(0);
        const text = option.description ? `${option.label} — ${option.description}` : option.label;
        if (chatRef.current) {
            chatRef.current.submitUserMessage({
                text,
                html: text,
                custom: { selection: true, selectionId: option.id }
            });
        }
        setUserMessageHistory(prev => [...prev, text]);
    }, [chatRef]);

    const handleSendMessage = async (messageText) => {
        let rawMessageWithoutHtml = new DOMParser().parseFromString(messageText, "text/html").body.textContent;

        // Test commands for selection prompts
        if (rawMessageWithoutHtml.trim() === '/test-selections') {
            setSelectionPrompt({
                prompt: 'What type of chart would you like?',
                options: [
                    { id: 'bar', label: 'Bar Chart', description: 'Compare categories with rectangular bars' },
                    { id: 'line', label: 'Line Chart', description: 'Show trends over time or continuous data' },
                    { id: 'scatter', label: 'Scatter Plot', description: 'Reveal correlations between two variables' },
                    { id: 'pie', label: 'Pie Chart', description: 'Show proportions of a whole' },
                ],
            });
            setSelectionFocusIndex(0);
            return;
        }
        if (rawMessageWithoutHtml.trim() === '/test-selections-simple') {
            setSelectionPrompt({
                prompt: 'Would you like to apply this change?',
                options: [
                    { id: 'yes', label: 'Yes' },
                    { id: 'no', label: 'No' },
                ],
            });
            setSelectionFocusIndex(0);
            return;
        }

        // If user sends free text while a selection is active, clear the selection
        if (selectionPrompt && rawMessageWithoutHtml.trim() !== "") {
            setSelectionPrompt(null);
            setSelectionFocusIndex(0);
        }

        if (rawMessageWithoutHtml.trim() != "") {
            setUserMessageHistory(prev => [...prev, messageText]);
        }


        if (chatRef.current) {
            if (pendingFiles.length > 0) {
                try {
                    // Upload to store, then link via apply
                    const fileIds = await uploadFilesToStore(pendingFiles);
                    const roomId = currentRoom?.id;
                    if (roomId && fileIds.length > 0) {
                        await applyFileChanges(fileIds, []);
                    }

                    if (rawMessageWithoutHtml.trim() === "") {
                        const escapeHtml = (s) => String(s)
                            .replace(/&/g, '&amp;')
                            .replace(/</g, '&lt;')
                            .replace(/>/g, '&gt;')
                            .replace(/"/g, '&quot;')
                            .replace(/'/g, '&#39;');

                        const itemsHtml = pendingFiles.map(f => `<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">🗋 ${escapeHtml(f.name)}</span><br>`).join('\n');

                        messageText = `Uploaded file(s):\n${itemsHtml}`;
                        rawMessageWithoutHtml = new DOMParser().parseFromString(messageText, "text/html").body.textContent;
                    }
                    chatRef.current.submitUserMessage({ text: rawMessageWithoutHtml, html: messageText, custom: { upload: true } });
                    setPendingFiles([]);
                } catch (err) {
                    console.error("Error during file processing:", err);
                }
            } else {
                if (rawMessageWithoutHtml.trim() === "") return;
                chatRef.current.submitUserMessage({ text: rawMessageWithoutHtml, html: messageText, custom: { upload: false } });
            }

        }
    };

    const handleFileChange = (e) => {
        const files = Array.from(e.target.files);
        if (files.length > 0) setPendingFiles(prev => [...prev, ...files]);
        e.target.value = '';
    };
    const handleRemoveFile = (idx) => {
        setPendingFiles(prev => prev.filter((_, i) => i !== idx));
    };

	const handleDragOverInput = (e) => {
		e.preventDefault();
	};
	const handleInput = (e) => {
		if (!isInputEnabled) return;
		const el = e.target;
		// When the user deletes all text, browsers leave a residual <br> inside
		// the contentEditable div. Strip it so the :empty pseudo-class matches
		// and the CSS placeholder reappears.
		if (el.textContent.trim() === '' && el.innerHTML !== '') {
			el.innerHTML = '';
		}
		setCurrentMessage(el.innerHTML);
		const charCount = el.textContent.length;
		setIsSingleLine(charCount <= 45 && el.scrollHeight <= 65);
	};

    const insertPaletteTag = (paletteName) => {
        if (!customInputRef.current) return;

        customInputRef.current.focus();
        const sel = window.getSelection();
        if (!sel || sel.rangeCount === 0 || !customInputRef.current.contains(sel.anchorNode)) {
            focusAndPlaceCaretAtEnd(customInputRef.current);
        }

        if (paletteName) {
            const range = sel.getRangeAt(0);
            range.deleteContents();
            const span = document.createElement('span');
            span.className = 'palette-tag';
            span.contentEditable = 'false';
            span.style.cssText = 'color:#00ffc2; margin-right: 5px;';
            span.textContent = `#${paletteName}`;
            const spacer = document.createTextNode('\u00A0');
            range.insertNode(spacer);
            range.insertNode(span);
            range.setStartAfter(spacer);
            range.collapse(true);
            sel.removeAllRanges();
            sel.addRange(range);
            setCurrentMessage(customInputRef.current.innerHTML);
        }
    };

    return (
        <div className={styles.chatInput}>
            {uploadError && (
                <div className={styles.uploadErrorBanner}>
                    <span className={styles.uploadErrorIcon}>⚠️</span>
                    <span className={styles.uploadErrorContent}>
                        <span className={styles.uploadErrorText}>{uploadError}</span>
                        {hasBilling() && <a href="/plan" className={styles.uploadErrorLink}>{t("chat.upgradePlan")}</a>}
                    </span>
                    <button 
                        className={styles.uploadErrorClose}
                        onClick={() => setUploadError(null)}
                        aria-label="Close"
                    >
                        ×
                    </button>
                </div>
            )}

            {isDragActive && isInputEnabled && !isDataSourcesOpen && (
                <div
                    className={`${styles.csvDropOverlay} ${isDragActive ? styles.active : ''}`}
                    onDrop={e => {
                        e.preventDefault();
                        setIsDragActive(false);
                        let files = [];
                        if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                            files = Array.from(e.dataTransfer.files);
                        }
                        const validFiles = files.filter(file => {
                            const ext = file.name.toLowerCase().substring(file.name.lastIndexOf('.'));
                            return allowedExtensions.includes(ext) && file.size <= maxSize;
                        });
                        if (validFiles.length !== files.length && chatRef.current) {
                            const unsupportedExts = [...new Set(
                                files
                                    .filter(file => {
                                        const ext = file.name.toLowerCase().substring(file.name.lastIndexOf('.'));
                                        return !allowedExtensions.includes(ext) || file.size > maxSize;
                                    })
                                    .map(file => file.name.toLowerCase().substring(file.name.lastIndexOf('.')))
                            )];
                            const msg = t("unsupportedFileUpload", { extensions: unsupportedExts.join(", ") });
                            chatRef.current.submitUserMessage({ text: msg, html: msg, custom: { upload: false } });
                        }
                        if (validFiles.length > 0) {
						setPendingFiles(prev => [...prev, ...validFiles]);
						setIsDataSourcesOpen(true);
					}
                    }}
                    onDragOver={e => e.preventDefault()}
                >
                    {t("chat.upload.dropHere")}
                </div>
            )}
            <div className={styles.chatInputContainer}>
                {selectionPrompt && (
                    <SelectionPrompt
                        prompt={selectionPrompt.prompt}
                        options={selectionPrompt.options}
                        focusedIndex={selectionFocusIndex}
                        onSelect={handleSelectionSubmit}
                        onFocusChange={setSelectionFocusIndex}
                        escHint={t('chat.selectionEscHint')}
                    />
                )}
                {pendingFiles.length > 0 && (
                    <div
                        className={styles.fileDropZone}
                        onDragOver={handleDragOverInput}
                        onClick={() => fileInputRef.current && fileInputRef.current.click()}
                    >
                        <div className={styles.fileBadges}>

                            {pendingFiles.map((file, idx) => (
                                <span key={file.name + idx} className={styles.fileBadge}>
                                    {getFileIcon(file)}
                                    <span className={styles.fileName}>{file.name}</span>
                                    <button
                                        type="button"
                                        onClick={e => { e.stopPropagation(); handleRemoveFile(idx); }}
                                        className={styles.removeFileButton}
                                        data-tooltip={t("remove")}
                                        style={{ display: isUploading ? 'none' : 'inline' }}
                                    >
                                        ×
                                    </button>
                                </span>
                            ))}
                        </div>
                        <div className={styles.filesStatus}>
                            <div className={`${styles.filesStatusText} ${isUploading ? styles.dots : ''}`}>{filesStatus}</div>
                        </div>
                    </div>
                )}
                <input
                    ref={fileInputRef}
                    type="file"
                    style={{ display: 'none' }}
                    multiple
                    accept={allowedAccept}
                    onChange={handleFileChange}
                    tabIndex={-1}
                />
                {!selectionPrompt && (
                <>
                <div className={styles.chatOptions}>
                    <div data-tooltip={t('chat.autoRefresh', 'Auto-refresh interval')}>
                        <Select
                            options={[
                                { value: null, label: 'Off' },
                                { value: 5, label: '5s' },
                                { value: 10, label: '10s' },
                                { value: 30, label: '30s' },
                                { value: 60, label: '1m' },
                                { value: 300, label: '5m' },
                                { value: 900, label: '15m' },
                            ]}
                            value={
                                refreshInterval
                                    ? { value: refreshInterval, label: refreshInterval >= 60 ? `${refreshInterval / 60}m` : `${refreshInterval}s` }
                                    : { value: null, label: 'Off' }
                            }
                            onChange={opt => handleSetRefreshInterval(opt?.value ?? null)}
                            menuPlacement="top"
                            isSearchable={false}
                            isDisabled={!isInputEnabled}
                            theme={darkSelectTheme}
                            components={{
                                ValueContainer: ({ children, ...props }) => (
                                    <div style={{ display: 'flex', alignItems: 'center', padding: '0 4px' }}>
                                        <span style={{ color: '#888', marginRight: 2, fontSize: '1rem', lineHeight: 1 }}>{'\u21BA'}</span>
                                        {children}
                                    </div>
                                ),
                            }}
                            styles={mergeSelectStyles({
                                container: (base) => ({ ...base, width: 90 }),
                                control: (base) => ({
                                    ...base,
                                    backgroundColor: 'transparent',
                                    borderRadius: '8px',
                                    border: '0px!important',
                                    boxShadow: 'none!important',
                                    minHeight: 30,
                                    cursor: 'pointer',
                                }),
                                singleValue: (base) => ({ ...base, color: '#b0b0b0', fontSize: '0.82rem' }),
                                dropdownIndicator: (base) => ({ ...base, padding: '0 4px', color: '#666' }),
                                menu: (base) => ({ ...base, width: 90, minWidth: 90 }),
                                menuList: (base) => ({ ...base, overflowX: 'hidden' }),
                                option: (base, state) => ({
                                    ...base,
                                    fontSize: '0.82rem',
                                    padding: '6px 12px',
                                    width: 'unset',
                                    margin: '2px 4px',
                                }),
                            })}
                        />
                    </div>
                    <PaletteMenu onSelect={insertPaletteTag} />
                    {linkedFiles.length > 0 && (
                        <FilePills files={linkedFiles} onClick={() => setIsDataSourcesOpen(true)} />
                    )}
                </div>
                {isUploading && (
                    <progress ref={uploadProgressRef} value="0" max="100" className="progress-bar-indicator" style={{ width: '100%' }}></progress>
                )}
                </>
                )}
                {isGuest && (
                    <div className={styles.guestCTA}>
                        <span className={styles.guestCTAText}>{t('guest.limitWarningDescription')}</span>
                        <button className={styles.guestCTAButton} onClick={() => setShowAuthModal(true)}>
                            {t('guest.signUpFree')}
                        </button>
                    </div>
                )}
                <div
                    className={`${styles.inputWrapper} ${isSingleLine ? "" : styles.multiLine} ${selectionPrompt ? styles.inputWrapperSelection : ""} ${selectionPrompt && selectionFocusIndex === selectionPrompt.options.length ? styles.inputWrapperSelectionFocused : ""}`}
                    onMouseEnter={selectionPrompt ? () => setSelectionFocusIndex(selectionPrompt.options.length) : undefined}
                    onClick={selectionPrompt ? () => { setSelectionFocusIndex(selectionPrompt.options.length); customInputRef.current?.focus(); } : undefined}
                >
                    {isSingleLine && !selectionPrompt && (
                        <>
                            <button
                                id="chat-upload-button"
                                type="button"
                                className={styles.uploadButton}
                                onClick={() => setIsDataSourcesOpen(true)}
                                tabIndex={0}
                                disabled={!isInputEnabled || isGuest}
								data-tooltip={t("chat.dataSources")}
                                style={isGuest ? { opacity: 0.4 } : undefined}
                            >
                                <BsPaperclip />
                            </button>
                            <button
                                type="button"
                                className={styles.variablePickerButton}
                                onMouseDown={() => {
                                    const sel = window.getSelection();
                                    if (sel && sel.rangeCount > 0 && customInputRef.current?.contains(sel.anchorNode)) {
                                        savedRangeRef.current = sel.getRangeAt(0).cloneRange();
                                    }
                                }}
                                onClick={() => {
                                    if (datasets.length > 0) {
                                        isVariablePickerOpenRef.current = true;
                                        setVariablePickerFilter('');
                                        setIsVariablePickerOpen(true);
                                    }
                                }}
                                tabIndex={0}
                                disabled={!isInputEnabled || datasets.length === 0}
                                data-tooltip={t("chat.inputPlaceholder")}
                            >
                                @
                            </button>
                        </>
                    )}
                    {selectionPrompt && (
                        <>
                            <div className={`${styles.selectionRadioCircle} ${selectionFocusIndex === selectionPrompt.options.length ? styles.selectionRadioCircleFocused : ''}`} />
                            <span className={styles.selectionOtherLabel}>{t('chat.selectionOther')}</span>
                        </>
                    )}
                    <div
                        ref={customInputRef}
                        value={currentMessage}
                        suppressContentEditableWarning
                        onInput={handleInput}
                        onKeyDown={handleKeyDown}
                        onPaste={handlePaste}
                        placeholder={selectionPrompt ? t("chat.selectionPlaceholder") : (!isAuthenticated ? t("chat.loginToChat") : !isRoomReady ? t("chat.waitingForRoom") : t("chat.inputPlaceholder"))}
                        className={`${styles.chatInputText} ${selectionPrompt && selectionFocusIndex !== selectionPrompt.options.length ? styles.chatInputTextNoCaret : ''}`}
                        rows="1"
                        style={isGuest ? { opacity: 0.4, pointerEvents: 'none' } : undefined}
                    ></div>
                    {isSingleLine ? (
                        <button
                            type="button"
                            className={styles.sendButton}
                            onClick={() => {
                                if (isWaitingForResponse) {
                                    // stop
                                }
                                else if (currentMessage.trim()) {
                                    handleSendMessage(currentMessage.trim());
                                    setCurrentMessage('');
                                    setHistoryIndex(-1);
                                    setTempMessage('');
                                    customInputRef.current.textContent = '';
									setIsSingleLine(true);
                                    setTimeout(() => {
                                        customInputRef.current.focus();
                                    }, 100);
                                }
                            }}
                            tabIndex={0}
                            disabled={!isInputEnabled || isGuest}
                            style={isGuest ? { opacity: 0.4 } : undefined}
                        >
                            {isWaitingForResponse ? <HiStop /> : <PiPaperPlaneRightFill />}
                        </button>
                    ) : (
                        <div className={styles.buttonRow}>
                            {!selectionPrompt && (
                            <div style={{ display: 'flex', alignItems: 'center' }}>
                                <button
                                    id="chat-upload-button"
                                    type="button"
                                    className={styles.uploadButton}
                                    onClick={() => setIsDataSourcesOpen(true)}
                                    tabIndex={0}
                                    disabled={!isInputEnabled || isGuest}
									data-tooltip={t("chat.dataSources")}
                                    style={isGuest ? { opacity: 0.4 } : undefined}
                                >
                                    <BsPaperclip />
                                </button>
                                <button
                                    type="button"
                                    className={styles.variablePickerButton}
                                    onMouseDown={() => {
                                        const sel = window.getSelection();
                                        if (sel && sel.rangeCount > 0 && customInputRef.current?.contains(sel.anchorNode)) {
                                            savedRangeRef.current = sel.getRangeAt(0).cloneRange();
                                        }
                                    }}
                                    onClick={() => {
                                        if (datasets.length > 0) {
                                            isVariablePickerOpenRef.current = true;
                                            setVariablePickerFilter('');
                                            setIsVariablePickerOpen(true);
                                        }
                                    }}
                                    tabIndex={0}
                                    disabled={!isInputEnabled || datasets.length === 0}
                                    data-tooltip={t("chat.inputPlaceholder")}
                                >
                                    @
                                </button>
                            </div>
                            )}
                            <button
                                type="button"
                                className={styles.sendButton}
                                onClick={() => {
                                    if (isWaitingForResponse) {
                                        // stop
                                    }
                                    else if (currentMessage.trim()) {
                                        handleSendMessage(currentMessage.trim());
                                        setCurrentMessage('');
                                        setHistoryIndex(-1);
                                        setTempMessage('');
                                        if (customInputRef.current) customInputRef.current.textContent = '';
										setIsSingleLine(true);
                                        scheduleRefocus();
                                    }
                                }}
                                tabIndex={0}
                                disabled={!isInputEnabled || isGuest}
                                style={isGuest ? { opacity: 0.4 } : undefined}
                            >
                                {isWaitingForResponse ? <HiStop /> : <PiPaperPlaneRightFill />}
                            </button>
                        </div>
                    )}
                </div>
                <span className={styles.aiNotice}>{t('chat.aiNotice')}</span>
            </div>

			<DataSourcesModal
				isOpen={isDataSourcesOpen}
				onClose={() => setIsDataSourcesOpen(false)}
				t={t}
				datasets={datasets}
				hasUrlSources={hasUrlSources}
				refreshInterval={refreshInterval}
				pendingFiles={pendingFiles}
				setPendingFiles={setPendingFiles}
				onUploadFiles={uploadFilesToStore}
				onLoadUrl={uploadUrlToStore}
				onApplyChanges={applyFileChanges}
				onRefresh={handleRefreshUrlSources}
				onSetRefreshInterval={handleSetRefreshInterval}
				fileInputRef={fileInputRef}
				isUploading={isUploading}
				isUrlLoading={isUrlLoading}
				isRefreshing={isRefreshing}
				filesStatus={filesStatus}
				uploadError={uploadError}
				clearUploadError={() => setUploadError(null)}
				userFiles={userFiles}
				fetchUserFiles={fetchUserFiles}
			/>

            <VariablePickerModal
                isOpen={isVariablePickerOpen}
                onClose={() => {
                    isVariablePickerOpenRef.current = false;
                    setIsVariablePickerOpen(false);
                    savedRangeRef.current = null;
                    scheduleRefocus();
                }}
                onSelect={insertVariable}
                datasets={datasets}
                initialFilter={variablePickerFilter}
                t={t}
            />
        </div >
    );
}));

export default CustomInput;
