// SPDX-FileCopyrightText: 2025 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-FileContributor: Guillaume Franque
// SPDX-FileContributor: Clément Baraille
// SPDX-License-Identifier: AGPL-3.0-or-later

// NavBar is rendered globally in App.jsx
import styles from "./Settings.module.css";
import Select from 'react-select';
import { useState, useEffect, useRef } from 'react';
import { mergeSelectStyles, darkSelectTheme } from "../utils/selectStyles";
import { useTranslation } from 'react-i18next';
import { useAuth } from "../Auth/AuthContext";
import { IoPersonCircle, IoSettingsOutline } from "react-icons/io5";
import { RiLockPasswordLine } from "react-icons/ri";
import { MdKey, MdContentCopy, MdDelete } from "react-icons/md";
import { useNavigate, Link } from 'react-router-dom';
import { hasBilling, getLicenseDisplay } from '../extensions';

const countries = [
    { value: 'EN', label: '🇺🇸 - English' },
    { value: 'FR', label: '🇫🇷 - French' },
];

const ai_tone_options = [
    { value: "friendly", label: "Friendly" },
    { value: "neutral", label: "Neutral" },
    { value: "enthusiastic", label: "Enthusiastic" },
    { value: "academic", label: "Academic" },
    { value: "jarvis", label: "J.A.R.V.I.S." }
];

const settingsSelectStyles = mergeSelectStyles({
    container: (base) => ({ ...base, width: '100%' }),
    control: (base, state) => ({
        ...base,
        backgroundColor: "rgba(255, 255, 255, 0.05)",
        borderRadius: "10px",
        outline: 'none',
        border: "1px solid rgba(255, 255, 255, 0.08)",
        borderColor: state.isFocused ? 'rgba(27, 144, 186, 0.5)' : 'rgba(255, 255, 255, 0.08)',
        boxShadow: 'none',
        ':hover': { borderColor: 'rgba(27, 144, 186, 0.3)' },
    }),
});

const StyledSelect = ({ options, value, onChange, placeholder, menuPlacement = 'auto', isDisabled, inputId }) => {
    const selectedOption = options.find(o => o.value === value) || null;
    return (
        <Select
            inputId={inputId}
            placeholder={placeholder}
            options={options}
            value={selectedOption}
            onChange={opt => onChange(opt ? opt.value : null)}
            menuPlacement={menuPlacement}
            isDisabled={isDisabled}
            theme={darkSelectTheme}
            styles={settingsSelectStyles}
            menuPortalTarget={typeof document !== 'undefined' ? document.body : null}
        />
    );
};

const LICENSE_LABELS = { free: "Free", pro: "Pro", enterprise: "Enterprise" };

export default function Settings() {
    const { t, i18n } = useTranslation();
    const { user, isAuthenticated, isGuest, secureRequest, logout } = useAuth();
    const navigate = useNavigate();

    const [isLoading, setIsLoading] = useState(false);
    const [selectedOption, setSelectedOption] = useState(() => {
        const currentLang = i18n.language.toUpperCase();
        return countries.find(c => c.value === currentLang) || countries[0];
    });
    const [aiTone, setAiTone] = useState("neutral");
    const [savingTone, setSavingTone] = useState(false);
    const toneDebounceRef = useRef(null);

    const [showPasswordModal, setShowPasswordModal] = useState(false);
    const [currentPassword, setCurrentPassword] = useState("");
    const [newPassword, setNewPassword] = useState("");
    const [confirmPassword, setConfirmPassword] = useState("");
    const [passwordError, setPasswordError] = useState("");
    const [passwordSuccess, setPasswordSuccess] = useState("");
    const [savingPassword, setSavingPassword] = useState(false);

    const [showDeleteModal, setShowDeleteModal] = useState(false);
    const [deletingAccount, setDeletingAccount] = useState(false);
    const [deleteError, setDeleteError] = useState("");

    // API Keys state
    const [apiKeys, setApiKeys] = useState([]);
    const [showCreateKeyModal, setShowCreateKeyModal] = useState(false);
    const [newKeyName, setNewKeyName] = useState("");
    const [createdKeyValue, setCreatedKeyValue] = useState(null);
    const [creatingKey, setCreatingKey] = useState(false);
    const [copiedKeyId, setCopiedKeyId] = useState(null);

    const [licenseInfo, setLicenseInfo] = useState(null);
    const [syncingLicense, setSyncingLicense] = useState(false);

    useEffect(() => {
        if (!isAuthenticated || isGuest || !hasBilling()) return;
        let cancelled = false;
        setSyncingLicense(true);
        secureRequest("/server/license/sync", { method: "GET" })
            .then(res => res.ok ? res.json() : null)
            .then(data => { if (!cancelled && data) setLicenseInfo(data); })
            .catch(() => {})
            .finally(() => { if (!cancelled) setSyncingLicense(false); });
        return () => { cancelled = true; };
    }, [isAuthenticated, isGuest]);

    // Generic single-key sender (currently only used for ai_tone)
    const updateSetting = async (key, value) => {
        if (key !== "ai_tone") return; // guard: only ai_tone for now
        setSavingTone(true);
        try {
            await secureRequest("/server/user/settings", {
                method: "POST",
                body: JSON.stringify({ [key]: value })
            });
        } catch (e) {
            console.error(`Failed to update ${key}:`, e);
        } finally {
            setSavingTone(false);
        }
    };

    // Fetch ai_tone from merged settings (server + AI service)
    const fetchUserSettings = async () => {
        if (!isAuthenticated) return;
        setIsLoading(true);
        try {
            const res = await secureRequest("/server/user/settings", { method: "GET" });
            if (res.ok) {
                const data = await res.json();
                const tone = data?.settings?.ai_tone;
                if (typeof tone === "string" && tone.length > 0) {
                    setAiTone(tone);
                }
            }
        } catch (e) {
            console.error("Failed to fetch settings:", e);
        } finally {
            setIsLoading(false);
        }
    };

    // Fetch API keys
    const fetchApiKeys = async () => {
        if (!isAuthenticated || isGuest) return;
        try {
            const res = await secureRequest("/api/v1/keys", { method: "GET" });
            if (res.ok) {
                const data = await res.json();
                setApiKeys(data || []);
            }
        } catch (e) {
            console.error("Failed to fetch API keys:", e);
        }
    };

    const handleCreateKey = async (e) => {
        e.preventDefault();
        if (!newKeyName.trim()) return;
        setCreatingKey(true);
        try {
            const res = await secureRequest("/api/v1/keys", {
                method: "POST",
                body: JSON.stringify({ name: newKeyName.trim() }),
            });
            if (res.ok) {
                const data = await res.json();
                setCreatedKeyValue(data.key_value);
                setNewKeyName("");
                fetchApiKeys();
            }
        } catch (e) {
            console.error("Failed to create API key:", e);
        } finally {
            setCreatingKey(false);
        }
    };

    const handleRevokeKey = async (keyId) => {
        try {
            const res = await secureRequest(`/api/v1/keys/${keyId}`, { method: "DELETE" });
            if (res.ok) {
                setApiKeys(prev => prev.filter(k => k.id !== keyId));
            }
        } catch (e) {
            console.error("Failed to revoke API key:", e);
        }
    };

    const copyToClipboard = (text, keyId) => {
        navigator.clipboard.writeText(text);
        setCopiedKeyId(keyId);
        setTimeout(() => setCopiedKeyId(null), 2000);
    };

    useEffect(() => {
        fetchUserSettings();
        fetchApiKeys();
    }, [isAuthenticated]);

    // Debounced ai tone change
    const handleAiToneChange = (value) => {
        setAiTone(value);
        if (toneDebounceRef.current) clearTimeout(toneDebounceRef.current);
        toneDebounceRef.current = setTimeout(() => {
            updateSetting("ai_tone", value);
        }, 250);
    };

    useEffect(() => {
        return () => {
            if (toneDebounceRef.current) clearTimeout(toneDebounceRef.current);
        };
    }, []);

    // Language select remains local only (no persistence yet)
    useEffect(() => {
        const currentLang = i18n.language.toUpperCase();
        setSelectedOption(countries.find(c => c.value === currentLang) || countries[0]);
    }, [i18n.language]);

    const resetPasswordForm = () => {
        setCurrentPassword("");
        setNewPassword("");
        setConfirmPassword("");
        setPasswordError("");
        setPasswordSuccess("");
    };

    const openPasswordModal = () => {
        resetPasswordForm();
        setShowPasswordModal(true);
    };

    const closePasswordModal = () => {
        if (!savingPassword) {
            setShowPasswordModal(false);
            resetPasswordForm();
        }
    };

    const handlePasswordChange = async (e) => {
        e.preventDefault();
        setPasswordError("");
        setPasswordSuccess("");

        if (!currentPassword) {
            setPasswordError(t("settings.currentPasswordRequired"));
            return;
        }
        if (newPassword.length < 8) {
            setPasswordError(t("auth.passwordMinError"));
            return;
        }
        if (newPassword !== confirmPassword) {
            setPasswordError(t("auth.passwordMismatch"));
            return;
        }
        if (currentPassword === newPassword) {
            setPasswordError(t("auth.passwordSameAsOld"));
            return;
        }

        setSavingPassword(true);
        try {
            const response = await secureRequest("/server/auth/change-password", {
                method: "POST",
                body: JSON.stringify({
                    email: user.email,
                    current_password: currentPassword,
                    new_password: newPassword
                }),
            });

            if (response.ok) {
                setPasswordSuccess(t("settings.passwordChanged"));
                setCurrentPassword("");
                setNewPassword("");
                setConfirmPassword("");
            } else {
                const data = await response.json();
                setPasswordError(data.detail || t("settings.passwordChangeFailed"));
            }
        } catch (err) {
            setPasswordError(err.message || t("settings.passwordChangeFailed"));
        } finally {
            setSavingPassword(false);
        }
    };

    const handleDeleteAccount = async () => {
        setDeletingAccount(true);
        setDeleteError("");
        try {
            const url = `/server/auth/delete-account`;
            const response = await secureRequest(url, { method: "DELETE" });
            if (response.ok) {
                setShowDeleteModal(false);
                logout();
            } else {
                const data = await response.json();
                setDeleteError(data.detail || t("settings.deleteAccountError"));
            }
        } catch (err) {
            setDeleteError(err.message || t("settings.deleteAccountError"));
        } finally {
            setDeletingAccount(false);
        }
    };

    useEffect(() => {
        if (!isAuthenticated || isGuest) {
            navigate('/', { replace: true });
        }
    }, [isAuthenticated, isGuest, navigate]);

    // Don't render anything while redirecting
    if (!isAuthenticated || isGuest) {
        return null;
    }

    const licenseName = licenseInfo?.license_name || user?.license;
    const planLabel = LICENSE_LABELS[licenseName?.toLowerCase()] || licenseName || "Free";

    return (
        <div className={styles.page}>
            <div className={styles.backdrop}>
                <div className={styles.contentColumn}>
                    <div className={styles.header}>
                        <IoSettingsOutline className={styles.headerIcon} />
                        <h1 className={styles.title}>{t("settings.title")}</h1>
                    </div>

                    <div className={styles.profileCard}>
                        <IoPersonCircle className={styles.profileIcon} />
                        <div className={styles.profileInfo}>
                            <span className={styles.profileName}>{user?.name || user?.email}</span>
                            {user?.name && user?.email && (
                                <span className={styles.profileEmail}>{user.email}</span>
                            )}
                        </div>
                    </div>

                    <div className={styles.settingsGroup} style={{ animationDelay: '0.05s', zIndex: 5 }}>
                        <div className={styles.groupTitle}>{t("settings.general")}</div>
                        <div className={styles.settingItem}>
                            <label className={styles.settingLabel}>{t("settings.language")}</label>
                            <Select
                                value={selectedOption}
                                onChange={(option) => {
                                    setSelectedOption(option);
                                    i18n.changeLanguage(option.value.toLowerCase());
                                }}
                                options={countries}
                                theme={darkSelectTheme}
                                styles={settingsSelectStyles}
                                menuPortalTarget={typeof document !== 'undefined' ? document.body : null}
                            />
                        </div>
                    </div>

                    <div className={styles.settingsGroup} style={{ animationDelay: '0.1s', zIndex: 4 }}>
                        <div className={styles.groupTitle}>{t("settings.aiPreferences")}</div>
                        <div className={styles.settingItem}>
                            <label htmlFor="aiTone" className={styles.settingLabel}>{t("settings.aiTone")}</label>
                            <StyledSelect
                                inputId="aiTone"
                                options={ai_tone_options}
                                value={aiTone}
                                onChange={handleAiToneChange}
                                placeholder={t("settings.aiTonePlaceholder")}
                            />
                            {savingTone && (
                                <span className={styles.savingHint}>{t("settings.saving")}</span>
                            )}
                        </div>
                    </div>

                    <div className={styles.settingsGroup} style={{ animationDelay: '0.15s', zIndex: 2 }}>
                        <div className={styles.groupTitle}>{t("settings.subscription")}</div>
                        {(() => {
                            const ExtLicenseDisplay = getLicenseDisplay();
                            if (ExtLicenseDisplay) {
                                return <ExtLicenseDisplay user={user} planLabel={planLabel} licenseInfo={licenseInfo} styles={styles} />;
                            }
                            return (
                                <div className={styles.subscriptionRow}>
                                    <div className={styles.subscriptionInfo}>
                                        <span className={styles.settingLabel}>{t("settings.currentPlan")}</span>
                                        <span className={styles.planBadge}>
                                            {syncingLicense ? t("settings.loading") : planLabel}
                                        </span>
                                    </div>
                                    {hasBilling() && (
                                        <Link to="/plan" className={styles.managePlanLink}>
                                            {t("settings.managePlan")}
                                        </Link>
                                    )}
                                </div>
                            );
                        })()}
                    </div>

                    <div className={styles.settingsGroup} style={{ animationDelay: '0.2s', zIndex: 1 }}>
                        <div className={styles.groupTitle}>
                            <RiLockPasswordLine style={{ marginRight: "8px" }} />
                            {t("settings.security")}
                        </div>
                        <div className={styles.securityRow}>
                            <span className={styles.securityDescription}>
                                {t("settings.changePasswordDescription")}
                            </span>
                            <button
                                className={styles.changePasswordButton}
                                onClick={openPasswordModal}
                            >
                                {t("settings.changePassword")}
                            </button>
                        </div>
                    </div>

                    {/* API Keys Section */}
                    {!isGuest && (
                        <div className={styles.settingsGroup} style={{ animationDelay: '0.22s', zIndex: 1 }}>
                            <div className={styles.groupTitle}>
                                <MdKey style={{ marginRight: "8px" }} />
                                {t("settings.apiKeys", "API Keys")}
                            </div>
                            <p style={{ color: '#999', fontSize: '0.85rem', margin: '0 0 16px 0' }}>
                                {t("settings.apiKeysDescription", "Manage API keys for programmatic access to NVEIL.")}
                            </p>

                            {apiKeys.length > 0 && (
                                <div className={styles.apiKeysTable}>
                                    {apiKeys.map(k => (
                                        <div key={k.id} className={styles.apiKeyRow}>
                                            <div className={styles.apiKeyInfo}>
                                                <span className={styles.apiKeyName}>{k.name}</span>
                                                <span className={styles.apiKeyValue}>
                                                    {k.key_prefix}••••••••
                                                </span>
                                                <span className={styles.apiKeyMeta}>
                                                    {t("settings.apiKeyCreated", "Created")}: {k.created_at ? new Date(k.created_at).toLocaleDateString() : "—"}
                                                    {" · "}
                                                    {t("settings.apiKeyGenerations", "Generations")}: {k.total_generations || 0}
                                                    {k.last_used_at && (
                                                        <>{" · "}{t("settings.apiKeyLastUsed", "Last used")}: {new Date(k.last_used_at).toLocaleDateString()}</>
                                                    )}
                                                </span>
                                            </div>
                                            <div className={styles.apiKeyActions}>
                                                <button
                                                    className={`${styles.apiKeyActionBtn} ${styles.apiKeyDeleteBtn}`}
                                                    onClick={() => handleRevokeKey(k.id)}
                                                    data-tooltip={t("settings.revokeKey", "Revoke")}
                                                >
                                                    <MdDelete />
                                                </button>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}

                            <button
                                className={styles.changePasswordButton}
                                onClick={() => { setShowCreateKeyModal(true); setCreatedKeyValue(null); }}
                                style={{ marginTop: '12px' }}
                            >
                                + {t("settings.createApiKey", "Create API Key")}
                            </button>
                        </div>
                    )}

                    {/* Create API Key Modal */}
                    {showCreateKeyModal && (
                        <div className={styles.modalOverlay} onClick={() => setShowCreateKeyModal(false)}>
                            <div className={styles.modalGlassBg} onClick={e => e.stopPropagation()}>
                                <div className={styles.modalContentCompact}>
                                    <h3 className={styles.modalTitleCompact}>
                                        {createdKeyValue
                                            ? t("settings.apiKeyCreatedTitle", "API Key Created")
                                            : t("settings.createApiKeyTitle", "Create API Key")}
                                    </h3>
                                    {createdKeyValue ? (
                                        <div>
                                            <p className={styles.modalText}>
                                                {t("settings.apiKeyCreatedDesc", "Your API key has been created. Copy it now — it will not be shown again.")}
                                            </p>
                                            <div style={{
                                                background: 'rgba(255,255,255,0.05)',
                                                borderRadius: '8px',
                                                padding: '12px',
                                                fontFamily: 'monospace',
                                                fontSize: '0.85rem',
                                                color: '#1b90ba',
                                                wordBreak: 'break-all',
                                                marginBottom: '16px',
                                            }}>
                                                {createdKeyValue}
                                            </div>
                                            <div className={styles.modalActionsCompact}>
                                                <button
                                                    className={styles.changePasswordButton}
                                                    onClick={() => copyToClipboard(createdKeyValue, 'new')}
                                                >
                                                    <MdContentCopy style={{ marginRight: '6px' }} />
                                                    {copiedKeyId === 'new' ? "Copied!" : t("settings.copyKey", "Copy Key")}
                                                </button>
                                                <button
                                                    className={styles.cancelButtonCompact}
                                                    onClick={() => setShowCreateKeyModal(false)}
                                                >
                                                    {t("settings.close", "Close")}
                                                </button>
                                            </div>
                                        </div>
                                    ) : (
                                        <form onSubmit={handleCreateKey}>
                                            <div style={{ marginBottom: '16px' }}>
                                                <label className={styles.settingLabel}>
                                                    {t("settings.apiKeyNameLabel", "Key Name")}
                                                </label>
                                                <input
                                                    className={styles.settingInputField}
                                                    value={newKeyName}
                                                    onChange={e => setNewKeyName(e.target.value)}
                                                    placeholder={t("settings.apiKeyNamePlaceholder", "e.g. My Python Script")}
                                                    autoFocus
                                                    required
                                                />
                                            </div>
                                            <div className={styles.modalActionsCompact}>
                                                <button
                                                    type="submit"
                                                    className={styles.changePasswordButton}
                                                    disabled={creatingKey || !newKeyName.trim()}
                                                >
                                                    {creatingKey ? t("settings.creating", "Creating...") : t("settings.createApiKey", "Create API Key")}
                                                </button>
                                                <button
                                                    type="button"
                                                    className={styles.cancelButtonCompact}
                                                    onClick={() => setShowCreateKeyModal(false)}
                                                >
                                                    {t("settings.cancel", "Cancel")}
                                                </button>
                                            </div>
                                        </form>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}

                    {isLoading && <div className={styles.loadingHint}>{t("settings.loading")}</div>}

                    <div className={styles.dangerSection} style={{ animationDelay: '0.25s' }}>
                        <div className={styles.dangerTitle}>{t("settings.dangerZone")}</div>
                        <button
                            className={styles.deleteAccountLink}
                            onClick={() => setShowDeleteModal(true)}
                        >
                            {t("settings.deleteAccount")}
                        </button>
                    </div>
                </div>
            </div>

            {/* ── Password Modal ── */}
            {showPasswordModal && (
                <div className={styles.modalOverlay} onClick={closePasswordModal}>
                    <div className={styles.modalGlassBg} onClick={e => e.stopPropagation()}>
                        <div className={styles.modalContentCompact}>
                            <h3 className={styles.modalTitleCompact}>
                                {t("settings.changePasswordTitle")}
                            </h3>
                            <form onSubmit={handlePasswordChange} className={styles.passwordForm}>
                                <input
                                    type="password"
                                    className={styles.settingInputField}
                                    value={currentPassword}
                                    onChange={(e) => setCurrentPassword(e.target.value)}
                                    placeholder={t("settings.currentPasswordPlaceholder")}
                                    disabled={savingPassword}
                                    autoFocus
                                />
                                <input
                                    type="password"
                                    className={styles.settingInputField}
                                    value={newPassword}
                                    onChange={(e) => setNewPassword(e.target.value)}
                                    placeholder={t("settings.newPasswordPlaceholder")}
                                    minLength={8}
                                    disabled={savingPassword}
                                />
                                <input
                                    type="password"
                                    className={styles.settingInputField}
                                    value={confirmPassword}
                                    onChange={(e) => setConfirmPassword(e.target.value)}
                                    placeholder={t("settings.confirmPasswordPlaceholder")}
                                    minLength={8}
                                    disabled={savingPassword}
                                />

                                {passwordError && (
                                    <p className={styles.errorMessage}>{passwordError}</p>
                                )}
                                {passwordSuccess && (
                                    <p className={styles.successMessage}>{passwordSuccess}</p>
                                )}

                                <div className={styles.modalActionsCompact}>
                                    <button
                                        type="button"
                                        className={styles.cancelButtonCompact}
                                        onClick={closePasswordModal}
                                        disabled={savingPassword}
                                    >
                                        {t("cancel")}
                                    </button>
                                    <button
                                        type="submit"
                                        className={styles.changePasswordButton}
                                        disabled={savingPassword || !currentPassword || !newPassword || !confirmPassword}
                                    >
                                        {savingPassword ? t("settings.saving") : t("settings.changePassword")}
                                    </button>
                                </div>
                            </form>
                        </div>
                    </div>
                </div>
            )}

            {showDeleteModal && (
                <div className={styles.modalOverlay} onClick={() => !deletingAccount && setShowDeleteModal(false)}>
                    <div className={styles.modalGlassBg} onClick={e => e.stopPropagation()}>
                        <div className={styles.modalContentCompact}>
                            <h3 className={styles.modalTitleCompact}>
                                {t("settings.deleteAccountTitle")}
                            </h3>
                            <p className={styles.modalText}>
                                {t("settings.deleteAccountWarning")}
                            </p>
                            <p className={styles.modalText}>
                                {t("settings.deleteAccountNoRefund")}
                            </p>

                            {deleteError && (
                                <p className={styles.errorMessageSmall}>{deleteError}</p>
                            )}

                            <div className={styles.modalActionsCompact}>
                                <button
                                    className={styles.cancelButtonCompact}
                                    onClick={() => setShowDeleteModal(false)}
                                    disabled={deletingAccount}
                                >
                                    {t("cancel")}
                                </button>
                                <button
                                    className={styles.confirmDeleteButtonCompact}
                                    onClick={handleDeleteAccount}
                                    disabled={deletingAccount}
                                >
                                    {deletingAccount ? t("settings.deleting") : t("settings.deleteAccountConfirm")}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
