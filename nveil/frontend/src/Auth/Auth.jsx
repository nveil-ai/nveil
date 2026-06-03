// SPDX-FileCopyrightText: 2025 NVEIL SAS
// SPDX-FileContributor: Guillaume Franque
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import styles from "./Auth.module.css";
import { useState, useMemo, useEffect } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from 'react-i18next';
import { useAuth } from "./AuthContext";
import { Button as AriaButton } from 'react-aria-components';
import Select from 'react-select';
import { getData } from 'country-list';
import { mergeSelectStyles, darkSelectTheme } from "../utils/selectStyles";
import { trackEvent, trackSignup } from "../utils/analytics";
import { GoogleOAuthProvider } from '@react-oauth/google';
import {
    LoginForm,
    ForgotPasswordForm,
    ResetPasswordForm,
    VerifyEmailForm,
    ChangePasswordForm,
    RegisterSteps,
} from "./AuthForms";


// --- Unified user field config ---
const USER_FIELDS = [
    // { formKey, apiKey, default, toApi, toForm }
    { form: "firstName", api: "first_name", default: "", toApi: v => v?.trim() || "", toForm: v => v || "" },
    { form: "lastName", api: "last_name", default: "", toApi: v => v?.trim() || "", toForm: v => v || "" },
    { form: "email", api: "email", default: "", toApi: v => v?.trim() || "", toForm: v => v || "" },
    { form: "password", api: "password", default: "", toApi: v => v || "", toForm: v => v || "" },
    { form: "country", api: "country", default: "", toApi: v => v || "", toForm: v => v || "" },
    { form: "profession", api: "profession", default: "", toApi: v => v?.trim() || "", toForm: v => v || "" },
    { form: "education", api: "education", default: "", toApi: v => v || "", toForm: v => v || "" },
    { form: "isProfessional", api: "is_professional", default: false, toApi: v => !!v, toForm: v => !!v },
    { form: "enterpriseName", api: "enterprise_name", default: "", toApi: v => v?.trim() || "", toForm: v => v || "" },
    { form: "phoneNumber", api: "phone_number", default: "", toApi: v => v?.trim() || "", toForm: v => v || "" },
    { form: "acceptCGU", api: "accept_cgu", default: false, toApi: v => !!v, toForm: v => !!v },
    { form: "acceptPrivacy", api: "accept_privacy", default: false, toApi: v => !!v, toForm: v => !!v },
    { form: "acceptCommunication", api: "accept_communication", default: false, toApi: v => !!v, toForm: v => !!v },
];

// --- DRY: Single source of truth for form fields and defaults ---
const FORM_DEFAULTS = USER_FIELDS.reduce((acc, f) => ({ ...acc, [f.form]: f.default }), {});
export const educationLevels = [
    { value: 'High School', label: 'High School' },
    { value: 'Bachelor\'s Degree', label: 'Bachelor\'s Degree' },
    { value: 'Master\'s Degree', label: 'Master\'s Degree' },
    { value: 'PhD', label: 'PhD' },
    { value: 'Other', label: 'Other' },
];

const authSelectStyles = mergeSelectStyles({
    container: (base) => ({ ...base, width: '100%' }),
    control: (base, state) => ({
        ...base,
        backgroundColor: "#f9f9f912",
        borderRadius: "8px",
        outline: 'none',
        border: "0px solid #000000",
        borderColor: state.isFocused ? 'white' : '#e0e0e00e',
        boxShadow: 'none',
        ':hover': { borderColor: 'white' },
    }),
});

export const StyledSelect = ({ options, value, onChange, placeholder, menuPlacement = 'auto', isDisabled }) => {
    const selectedOption = options.find(o => o.value === value) || null;
    return (
        <Select
            placeholder={placeholder}
            options={options}
            value={selectedOption}
            onChange={opt => onChange(opt ? opt.value : null)}
            menuPlacement={menuPlacement}
            isDisabled={isDisabled}
            theme={darkSelectTheme}
            styles={authSelectStyles}
        />
    );
};

export default function Auth({ isOpen, onClose, onLoginSuccess }) {
    const [mode, setMode] = useState("login"); // "login" | "register" | "complete-profile" | "verify-email" | "change-password"
    const [formStep, setFormStep] = useState(1);
    const [form, setForm] = useState({ ...FORM_DEFAULTS });
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);
    const [formError, setFormError] = useState("");
    const [missingFields, setMissingFields] = useState([]);
    const [profileUser, setProfileUser] = useState(null);
    const [verificationCode, setVerificationCode] = useState("");
    const [newPassword, setNewPassword] = useState("");
    const [confirmPassword, setConfirmPassword] = useState("");
    const [resetCode, setResetCode] = useState(""); // Code pour reset password
    const [successMessage, setSuccessMessage] = useState(""); // Message de succès
    const { t } = useTranslation();


    const { login, secureRequest, refetchUser, logout, isAuthenticated, isGuest, profileComplete, missingFields: ctxMissingFields, googleAuthClientId } = useAuth();
    const countryOptions = useMemo(() => getData().map(c => ({ value: c.name, label: c.name })), []);

    // Auto-open profile completion modal for non-guest authenticated users
    // whose profile is incomplete (e.g. after Google OAuth page refresh)
    useEffect(() => {
        if (isAuthenticated && !isGuest && profileComplete === false && mode !== "complete-profile") {
            // Fetch current user profile to pre-fill the form
            secureRequest("/server/auth/me").then(async (res) => {
                if (res.ok) {
                    const userData = await res.json();
                    setProfileUser(userData);
                    setForm(userToForm(userData));
                    setMissingFields(userData.missing_fields || ctxMissingFields || []);
                    setMode("complete-profile");
                    setFormStep(1);
                }
            }).catch(() => {
                // Fallback: open modal with context data only
                setMissingFields(ctxMissingFields || []);
                setMode("complete-profile");
                setFormStep(1);
            });
        }
    }, [isAuthenticated, isGuest, profileComplete]);

    // DRY: Reset all forms and state
    const resetForms = () => {
        setForm({ ...FORM_DEFAULTS });
        setError("");
        setFormError("");
        setLoading(false);
        setFormStep(1);
        setMissingFields([]);
        setProfileUser(null);
        setNewPassword("");
        setConfirmPassword("");
    };

    // DRY: Map API user to form
    const userToForm = (user) =>
        USER_FIELDS.reduce(
            (acc, f) => ({ ...acc, [f.form]: f.toForm(user?.[f.api]) }),
            { ...FORM_DEFAULTS }
        );

    // DRY: Build payload for API
    const buildPayload = (fields, includePassword = true) => {
        const isProfileCompletion = mode === "complete-profile";
        let payload = {};

        if (isProfileCompletion && Array.isArray(fields) && fields.length > 0) {
            // Only include missing fields + email
            USER_FIELDS.forEach(f => {
                if (fields.includes(f.api) || f.api === "email") {
                    payload[f.api] = f.toApi(form[f.form]);
                }
            });
        } else {
            // Registration: include all fields
            USER_FIELDS.forEach(f => {
                if (f.api === "email" || (f.api !== "password" || includePassword)) {
                    payload[f.api] = f.toApi(form[f.form]);
                }
            });
            payload.name = `${form.firstName.trim()} ${form.lastName.trim()}`.trim();
        }
        return payload;
    };

    // Handle login (classic)
    const handleLogin = async (e) => {
        e.preventDefault();
        setError("");
        setLoading(true);
        try {
            const result = await login({ email: form.email, password: form.password });
            if (result.success) {
                if (result.profile_complete === false) {
                    setMode("complete-profile");
                    setMissingFields(result.missing_fields || []);
                    setProfileUser(result.user);
                    setForm(userToForm(result.user));
                    setFormStep(1);
                } else {
                    resetForms();
                    // setShowWelcome(true); removed
                    if (onLoginSuccess) onLoginSuccess();
                }
            } else if (result.requires_password_change) {
                // User needs to change their one-time password
                setMode("change-password");
                setForm(f => ({ ...f, email: result.email }));
                setError("");
            } else {
                setError(result.error || "Login failed");
            }
        } catch (err) {
            setError(err.message || "Invalid credentials");
        } finally {
            setLoading(false);
        }
    };

    // Handle Google login
    const handleGoogleLoginSuccess = async (credentialResponse) => {
        setLoading(true);
        setError("");
        try {
            const googleToken = credentialResponse.credential;
            const response = await secureRequest("/server/auth/google", {
                method: "POST",
                body: JSON.stringify({ idToken: googleToken }),
            });
            const result = await response.json();
            if (result.success) {
                if (result.profile_complete === false) {
                    setMode("complete-profile");
                    setMissingFields(result.missing_fields || []);
                    setProfileUser(result.user);
                    setForm(userToForm(result.user));
                    setFormStep(1);
                } else {
                    if (refetchUser) await refetchUser();
                    resetForms();
                    // setShowWelcome(true); removed
                    // onClose(); // Move this to after modal dismiss
                    if (onLoginSuccess) onLoginSuccess();
                }
            } else {
                setError(result.error || "Google login failed");
            }
        } catch (err) {
            setError(err.message || "Google login failed");
        } finally {
            setLoading(false);
        }
    };

    const handleVerifyEmail = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError("");
        try {
            const response = await secureRequest("/server/auth/verify-email", {
                method: "POST",
                body: JSON.stringify({ email: form.email, code: verificationCode }),
            });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || "Verification failed");
            }

            // Verification success, now login
            const loginResult = await login({
                email: form.email,
                password: form.password,
            });
            if (loginResult.success) {
                if (refetchUser) await refetchUser();
                resetForms();
                if (onLoginSuccess) onLoginSuccess();
                // setShowWelcome(true); removed
            } else {
                setMode("login");
                setError("Verification successful! Please log in.");
                resetForms();
            }
        } catch (err) {
            setError(err.message || "Verification failed");
        } finally {
            setLoading(false);
        }
    };

    const handleResendCode = async () => {
        setLoading(true);
        try {
            const response = await secureRequest("/server/auth/resend-verification", {
                method: "POST",
                body: JSON.stringify({ email: form.email }),
            });
            if (!response.ok) {
                if (response.status === 429) {
                    throw new Error(t("auth.rateLimitExceeded") || "Too many requests. Please wait a few minutes before trying again.");
                }
                throw new Error(t("auth.resendCodeFailed") || "Unable to resend the code. Please try again later.");
            }
            alert(t("auth.codeSent") || "Code sent!");
        } catch (err) {
            alert(err.message);
        } finally {
            setLoading(false);
        }
    };

    // Unified handler for registration and profile completion
    const handleFormSubmit = async () => {

        setFormError("");
        setLoading(true);
        try {
            let endpoint, payload;
            if (mode === "register") {
                endpoint = "/server/auth/register";
                payload = buildPayload();
            } else if (mode === "complete-profile") {
                endpoint = "/server/auth/complete-profile";
                payload = buildPayload(missingFields, false);
            }
            // console.log("Form state before submit:", form);
            // console.log("Missing fields:", missingFields);
            // console.log("Payload to submit:", payload);
            const response = await secureRequest(endpoint, {
                method: "POST",
                body: JSON.stringify(payload),
            });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || "Submission failed");
            }
            trackEvent("register_success", { method: "email" });
            trackSignup(form.email);
            const responseData = await response.json();

            if (mode === "register") {
                if (responseData.email_verified === false) {
                    setMode("verify-email");
                    setLoading(false);
                    return;
                }

                // After registration, auto-login
                const loginResult = await login({
                    email: form.email,
                    password: form.password,
                });
                if (loginResult.success) {
                    if (refetchUser) await refetchUser();
                    resetForms();
                    // onClose();
                    if (onLoginSuccess) onLoginSuccess();
                    // setShowWelcome(true); removed
                } else {
                    setMode("login");
                    setForm(f => ({ ...f, email: form.email }));
                    setError("Registration successful! Please log in.");
                    resetForms();
                }
            } else {
                // Profile completion
                if (refetchUser) await refetchUser();
                resetForms();
                // onClose();
                if (onLoginSuccess) onLoginSuccess();
                // setShowWelcome(true); removed
            }
        } catch (err) {
            setFormError(err.message || "Submission failed");
        } finally {
            setLoading(false);
        }
    };

    // Handle changes to form fields
    const handleFormChange = (value, name) => {
        setForm((prev) => ({ ...prev, [name]: value }));
    };

    // Step 1: Professional or Personal
    const handleAccountTypeSelect = (isProfessional) => {
        handleFormChange(isProfessional, "isProfessional");
        setFormStep(2);
    };

    const handleForgotPassword = async (e) => {
        e.preventDefault();
        setError("");
        setSuccessMessage("");

        if (!form.email) {
            setError(t("auth.emailRequired") || "Please enter your email address");
            return;
        }

        setLoading(true);
        try {
            const response = await secureRequest("/server/auth/forgot-password", {
                method: "POST",
                body: JSON.stringify({ email: form.email }),
            });

            if (response.ok) {
                // Passer au mode reset-password pour saisir le code
                setMode("reset-password");
                setSuccessMessage(t("auth.resetCodeSent") || "If an account exists with this email, a reset code has been sent.");
            } else {
                const data = await response.json();
                setError(data.detail || "Failed to send reset email");
            }
        } catch (err) {
            setError(err.message || "Failed to send reset email");
        } finally {
            setLoading(false);
        }
    };

    /**
     * Gère la réinitialisation du mot de passe avec le code reçu par email.
     */
    const handleResetPassword = async (e) => {
        e.preventDefault();
        setError("");
        setSuccessMessage("");

        // Validations
        if (!resetCode) {
            setError(t("auth.codeRequired") || "Please enter the verification code");
            return;
        }

        if (newPassword.length < 8) {
            setError(t("auth.passwordMinError") || "Password must be at least 8 characters");
            return;
        }

        if (newPassword !== confirmPassword) {
            setError(t("auth.passwordMismatch") || "Passwords do not match");
            return;
        }

        setLoading(true);
        try {
            const response = await secureRequest("/server/auth/reset-password", {
                method: "POST",
                body: JSON.stringify({
                    email: form.email,
                    code: resetCode,
                    new_password: newPassword
                }),
            });

            const result = await response.json();

            if (response.ok) {
                setForm({ ...FORM_DEFAULTS });
                setError("");
                setFormError("");
                setLoading(false);
                setFormStep(1);
                setMissingFields([]);
                setProfileUser(null);
                setNewPassword("");
                setConfirmPassword("");
                setResetCode("");
                // Now set the success message and mode AFTER clearing
                setMode("login");
                setSuccessMessage(t("auth.passwordResetSuccess") || "Password reset successfully!");
            } else {
                setError(result.detail || "Failed to reset password");
            }
        } catch (err) {
            setError(err.message || "Failed to reset password");
        } finally {
            setLoading(false);
        }
    };

    /**
     * Renvoie le code de réinitialisation par email.
     */
    const handleResendResetCode = async () => {
        setLoading(true);
        setError("");
        try {
            const response = await secureRequest("/server/auth/forgot-password", {
                method: "POST",
                body: JSON.stringify({ email: form.email }),
            });
            if (response.ok) {
                setSuccessMessage(t("auth.codeSent") || "A new code has been sent!");
            } else {
                setError("Failed to resend code");
            }
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const handleChangePassword = async (e) => {
        e.preventDefault();
        setError("");

        if (newPassword.length < 8) {
            setError(t("auth.passwordMinError") || "Password must be at least 8 characters");
            return;
        }

        if (newPassword !== confirmPassword) {
            setError(t("auth.passwordMismatch") || "Passwords do not match");
            return;
        }

        setLoading(true);
        try {
            const response = await secureRequest("/server/auth/change-password", {
                method: "POST",
                body: JSON.stringify({
                    email: form.email,
                    current_password: form.password,
                    new_password: newPassword
                }),
            });

            if (response.ok) {
                // Password changed, auto-login with new password
                const loginResult = await login({
                    email: form.email,
                    password: newPassword,
                });
                if (loginResult.success) {
                    resetForms();
                    if (onLoginSuccess) onLoginSuccess();
                } else {
                    resetForms();
                    setMode("login");
                    setSuccessMessage(t("auth.passwordChangeSuccess") || "Password changed successfully! Please log in.");
                }
            } else {
                const data = await response.json();
                setError(data.detail || "Failed to change password");
            }
        } catch (err) {
            setError(err.message || "Failed to change password");
        } finally {
            setLoading(false);
        }
    };

    if (!isOpen) return null;

    const handleLogout = () => {
        logout();
        onClose();
        setMode("login");
    };

    const modalContent = (
        <div className={styles.popupOverlay} onClick={() => {
            if (mode !== "complete-profile" && mode !== "change-password") onClose();
        }}>
            <div className={styles.modalGlassBg}>

                <div className={styles.popupContent} onClick={e => e.stopPropagation()}>
                    <h1 style={{ marginTop: 0, fontSize: "x-large", marginBottom: 30, fontWeight: 200 }}>
                        {mode === "login"
                            ? t("auth.signIn")
                            : mode === "register"
                                ? `${t("auth.signUp")} ${formStep === 1 ? t("auth.accountType") : formStep === 2 ? t("auth.accountDetails") : t("auth.profileInformation")}`
                                : mode === "verify-email"
                                    ? (t("auth.verifyEmail") || "Verify Email")
                                    : mode === "change-password"
                                        ? (t("auth.changePassword") || "Change Password")
                                        : mode === "forgot-password"
                                            ? (t("auth.forgotPassword") || "Forgot Password")
                                            : mode === "reset-password"
                                                ? (t("auth.resetPassword") || "Reset Password")
                                                : t("auth.completeProfile")}
                    </h1>
                    {mode !== "complete-profile" && mode !== "change-password" && (
                        <button onClick={onClose} className={styles.closeButton} disabled={loading}>✖</button>
                    )}
                    {successMessage && (
                        <p style={{ color: "#4ade80", textAlign: "center", marginBottom: "1em" }}>
                            {successMessage}
                        </p>
                    )}

                    {mode === "login" ? (
                        <LoginForm
                            form={form} setForm={setForm} loading={loading} error={error}
                            handleLogin={handleLogin} handleGoogleLoginSuccess={handleGoogleLoginSuccess}
                            setMode={setMode} setError={setError} setSuccessMessage={setSuccessMessage} t={t}
                            googleAuthEnabled={!!googleAuthClientId}
                        />
                    ) : mode === "forgot-password" ? (
                        <ForgotPasswordForm
                            form={form} setForm={setForm} loading={loading} error={error}
                            handleForgotPassword={handleForgotPassword} resetForms={resetForms}
                            setMode={setMode} t={t}
                        />
                    ) : mode === "reset-password" ? (
                        <ResetPasswordForm
                            form={form} loading={loading} error={error}
                            resetCode={resetCode} setResetCode={setResetCode}
                            newPassword={newPassword} setNewPassword={setNewPassword}
                            confirmPassword={confirmPassword} setConfirmPassword={setConfirmPassword}
                            handleResetPassword={handleResetPassword} handleResendResetCode={handleResendResetCode}
                            resetForms={resetForms} setMode={setMode} t={t}
                        />
                    ) : mode === "verify-email" ? (
                        <VerifyEmailForm
                            form={form} loading={loading} error={error}
                            verificationCode={verificationCode} setVerificationCode={setVerificationCode}
                            handleVerifyEmail={handleVerifyEmail} handleResendCode={handleResendCode} t={t}
                        />
                    ) : mode === "change-password" ? (
                        <ChangePasswordForm
                            loading={loading} error={error}
                            newPassword={newPassword} setNewPassword={setNewPassword}
                            confirmPassword={confirmPassword} setConfirmPassword={setConfirmPassword}
                            handleChangePassword={handleChangePassword} resetForms={resetForms}
                            setMode={setMode} t={t}
                        />
                    ) : (
                        <>
                            <RegisterSteps
                                mode={mode} formStep={formStep} setFormStep={setFormStep}
                                form={form} handleFormChange={handleFormChange}
                                handleFormSubmit={handleFormSubmit} handleAccountTypeSelect={handleAccountTypeSelect}
                                loading={loading} missingFields={missingFields}
                                countryOptions={countryOptions} t={t}
                            />
                            {formError && <p style={{ color: "red" }}>{formError}</p>}
                        </>
                    )}
                    {mode === "login" ? (
                        <p style={{ alignSelf: "center" }}>
                            {t("auth.notRegistered")}{" "}
                            <AriaButton
                                type="button"
                                className={styles.borderlessButton}
                                onPress={() => { setMode("register"); resetForms(); }}
                                isDisabled={loading}
                            >
                                {t("auth.registerHere")}
                            </AriaButton>
                        </p>
                    ) : mode === "register" ? (
                        <p>
                            {t("auth.alreadyRegistered")}{" "}
                            <AriaButton
                                type="button"
                                className={styles.borderlessButton}
                                onPress={() => setMode("login")}
                                isDisabled={loading}
                            >
                                {t("auth.signInHere")}
                            </AriaButton>
                        </p>
                    ) : null}
                    {(mode === "complete-profile" || mode === "change-password") ? (
                        <a onClick={handleLogout} style={{ width: "fit-content", placeSelf: "baseline", marginTop: "30px", textDecoration: "underline", cursor: "pointer" }} className={styles.textOnNavHovered}>{t("nav.logout")}</a>
                    ) : null}
                </div>
            </div>
        </div>
    );

    return createPortal(
        googleAuthClientId
            ? <GoogleOAuthProvider clientId={googleAuthClientId}>{modalContent}</GoogleOAuthProvider>
            : modalContent,
        document.body
    );
}
