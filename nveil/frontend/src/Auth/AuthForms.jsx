// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-FileContributor: Guillaume Franque
// SPDX-License-Identifier: AGPL-3.0-or-later

import styles from "./Auth.module.css";
import { useState, useEffect, useRef } from "react";
import { useTranslation, Trans } from 'react-i18next';
import { GoogleLogin } from '@react-oauth/google';
import {
    Button as AriaButton,
    Form as AriaForm,
    Input as AriaInput,
    Label as AriaLabel,
    TextField as AriaTextField,
    FieldError as AriaFieldError
} from 'react-aria-components';
import Checkbox from "../Components/Checkbox";
import { FaUser, FaBriefcase } from 'react-icons/fa';
import { StyledSelect, educationLevels } from "./Auth";

const FormStep = ({ children, onNext, onPrev, isLastStep, isLoading }) => {
    const [isInvalid, setInvalid] = useState(false);
    const alertRef = useRef(null);

    useEffect(() => {
        if (isInvalid) alertRef.current?.focus();
    }, [isInvalid]);

    const { t } = useTranslation();

    return (
        <AriaForm
            onInvalid={e => { e.preventDefault(); setInvalid(true); }}
            onSubmit={e => { e.preventDefault(); setInvalid(false); onNext(); }}
            onReset={() => setInvalid(false)}
            className={styles.loginForm}
        >
            {isInvalid && (
                <div role="alert" tabIndex={-1} ref={alertRef} className={styles.alert}>
                    <p>{t("auth.fixValidation")}</p>
                </div>
            )}
            {children}
            <div className={styles.stepNavigation}>
                {onPrev && <AriaButton type="button" onPress={onPrev} isDisabled={isLoading} className={styles.loginButton}>{t("auth.previous")}</AriaButton>}
                <AriaButton type="submit" isDisabled={isLoading} className={styles.loginButton}>
                    {isLoading ? "..." : (isLastStep ? t("auth.submit") : t("auth.next"))}
                </AriaButton>
            </div>
        </AriaForm>
    );
};

export function LoginForm({ form, setForm, loading, error, handleLogin, handleGoogleLoginSuccess, setMode, setError, setSuccessMessage, t, googleAuthEnabled }) {
    return (
        <form onSubmit={handleLogin} className={styles.loginForm}>
            <input
                className={styles.translucentInputField}
                type="email"
                name="email"
                placeholder={t("auth.email")}
                value={form.email}
                onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                disabled={loading}
                required
            />
            <input
                className={styles.translucentInputField}
                type="password"
                name="password"
                placeholder={t("auth.password")}
                value={form.password}
                onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                disabled={loading}
                required
                minLength="8"
            />
            <button type="submit" className={styles.loginButton} disabled={loading}>{loading ? t("auth.signIn") + "..." : t("auth.signIn")}</button>
            {error && <p style={{ color: "red" }}>{error}</p>}
            <button
                type="button"
                onClick={() => { setMode("forgot-password"); setError(""); setSuccessMessage(""); }}
                className={styles.borderlessButton}
                style={{ fontSize: "0.9em", marginTop: "0.5em" }}
            >
                {t("auth.forgotPasswordLink") || "Forgot your password?"}
            </button>

            {googleAuthEnabled && (
                <div style={{ marginTop: "1em", alignSelf: "center" }}>
                    <GoogleLogin
                        onSuccess={handleGoogleLoginSuccess}
                        onError={() => setError("Google login failed")}
                        width="100%"
                    />
                </div>
            )}
        </form>
    );
}

export function ForgotPasswordForm({ form, setForm, loading, error, handleForgotPassword, resetForms, setMode, t }) {
    return (
        <form onSubmit={handleForgotPassword} className={styles.loginForm}>
            <p style={{ color: "white", textAlign: "center", marginBottom: "20px" }}>
                {t("auth.forgotPasswordMessage") || "Enter your email address and we'll send you a code to reset your password."}
            </p>
            <input
                className={styles.translucentInputField}
                type="email"
                placeholder={t("auth.email")}
                value={form.email}
                onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                disabled={loading}
                required
            />
            <button type="submit" className={styles.loginButton} disabled={loading}>
                {loading ? "..." : (t("auth.sendResetCode") || "Send Reset Code")}
            </button>
            {error && <p style={{ color: "red" }}>{error}</p>}
            <button
                type="button"
                onClick={() => { resetForms(); setMode("login"); }}
                className={styles.borderlessButton}
                style={{ marginTop: "10px" }}
            >
                {t("auth.backToLogin") || "Back to Login"}
            </button>
        </form>
    );
}

export function ResetPasswordForm({ form, loading, error, resetCode, setResetCode, newPassword, setNewPassword, confirmPassword, setConfirmPassword, handleResetPassword, handleResendResetCode, resetForms, setMode, t }) {
    return (
        <form onSubmit={handleResetPassword} className={styles.loginForm}>
            <p style={{ color: "white", textAlign: "center", marginBottom: "20px" }}>
                {t("auth.enterResetCode") || `Enter the code sent to ${form.email} and your new password.`}
            </p>
            <input
                className={styles.translucentInputField}
                type="text"
                placeholder={t("auth.verificationCode") || "Verification Code"}
                value={resetCode}
                onChange={e => setResetCode(e.target.value)}
                disabled={loading}
                required
                maxLength="6"
                style={{ textAlign: "center", letterSpacing: "0.5em", fontSize: "1.2em" }}
            />
            <input
                className={styles.translucentInputField}
                type="password"
                placeholder={t("auth.newPassword") || "New Password (min. 8 characters)"}
                value={newPassword}
                onChange={e => setNewPassword(e.target.value)}
                disabled={loading}
                required
                minLength="8"
            />
            <input
                className={styles.translucentInputField}
                type="password"
                placeholder={t("auth.confirmPassword") || "Confirm Password"}
                value={confirmPassword}
                onChange={e => setConfirmPassword(e.target.value)}
                disabled={loading}
                required
                minLength="8"
            />
            <button type="submit" className={styles.loginButton} disabled={loading}>
                {loading ? "..." : (t("auth.resetPassword") || "Reset Password")}
            </button>
            {error && <p style={{ color: "red" }}>{error}</p>}

            <button
                type="button"
                onClick={handleResendResetCode}
                className={styles.borderlessButton}
                disabled={loading}
                style={{ marginTop: "10px", fontSize: "0.9em" }}
            >
                {t("auth.resendCode") || "Resend Code"}
            </button>

            <button
                type="button"
                onClick={() => { resetForms(); setMode("login"); }}
                className={styles.borderlessButton}
                style={{ marginTop: "5px" }}
            >
                {t("auth.backToLogin") || "Back to Login"}
            </button>
        </form>
    );
}

export function VerifyEmailForm({ form, loading, error, verificationCode, setVerificationCode, handleVerifyEmail, handleResendCode, t }) {
    return (
        <form onSubmit={handleVerifyEmail} className={styles.loginForm}>
            <p style={{ color: "white", textAlign: "center" }}>Please enter the verification code sent to {form.email}</p>
            <input
                className={styles.translucentInputField}
                type="text"
                placeholder="Verification Code"
                value={verificationCode}
                onChange={e => setVerificationCode(e.target.value)}
                disabled={loading}
                style={{ textAlign: "center" }}
                required
            />
            <button type="submit" className={styles.loginButton} disabled={loading}>
                {loading ? "Verifying..." : "Verify"}
            </button>
            <button
                type="button"
                onClick={handleResendCode}
                className={styles.borderlessButton}
                disabled={loading}
                style={{ marginTop: "10px", fontSize: "0.9em" }}
            >
                {t("auth.resendCode") || "Resend Code"}
            </button>
            {error && <p style={{ color: "red" }}>{error}</p>}
        </form>
    );
}

export function ChangePasswordForm({ loading, error, newPassword, setNewPassword, confirmPassword, setConfirmPassword, handleChangePassword, resetForms, setMode, t }) {
    return (
        <form onSubmit={handleChangePassword} className={styles.loginForm}>
            <p style={{ color: "white", textAlign: "center", marginBottom: "20px" }}>
                {t("auth.changePasswordMessage") || "Your password needs to be changed. Please enter a new password."}
            </p>
            <input
                className={styles.translucentInputField}
                type="password"
                placeholder={t("auth.newPassword") || "New Password"}
                value={newPassword}
                onChange={e => setNewPassword(e.target.value)}
                disabled={loading}
                required
                minLength="8"
            />
            <input
                className={styles.translucentInputField}
                type="password"
                placeholder={t("auth.confirmPassword") || "Confirm New Password"}
                value={confirmPassword}
                onChange={e => setConfirmPassword(e.target.value)}
                disabled={loading}
                required
                minLength="8"
            />
            <button type="submit" className={styles.loginButton} disabled={loading}>
                {loading ? "..." : (t("auth.changePassword") || "Change Password")}
            </button>
            {error && <p style={{ color: "red" }}>{error}</p>}
            <button
                type="button"
                onClick={() => { resetForms(); setMode("login"); }}
                className={styles.borderlessButton}
                style={{ marginTop: "10px" }}
            >
                {t("auth.backToLogin") || "Back to Login"}
            </button>
        </form>
    );
}

export function RegisterSteps({ mode, formStep, setFormStep, form, handleFormChange, handleFormSubmit, handleAccountTypeSelect, loading, missingFields, countryOptions, t }) {
    const isProfessional = !!form.isProfessional;
    const isProfileCompletion = mode === "complete-profile";
    const required = (field) => !isProfileCompletion || missingFields.includes(field);

    switch (formStep) {
        case 1:
            return (
                <div className={styles.loginForm}>
                    <p>{t("auth.howUseService")}</p>
                    <div className={styles.accountTypeContainer}>
                        <AriaButton className={styles.accountTypeButton} onPress={() => handleAccountTypeSelect(false)}>
                            <FaUser size={40} />
                            <span>{t("auth.personalUse")}</span>
                        </AriaButton>
                        <AriaButton className={styles.accountTypeButton} onPress={() => handleAccountTypeSelect(true)}>
                            <FaBriefcase size={40} />
                            <span>{t("auth.professionalUse")}</span>
                        </AriaButton>
                    </div>
                </div>
            );
        case 2:
            return (
                <FormStep
                    onNext={() => setFormStep(3)}
                    onPrev={() => setFormStep(1)}
                    isLoading={loading}
                >
                    <AriaTextField
                        name="firstName"
                        value={form.firstName}
                        onChange={v => handleFormChange(v, "firstName")}
                        isRequired={required("first_name")}
                        className={styles.inputArea}
                    >
                        <AriaLabel className={styles.fieldLabel}>{t("auth.firstName")}</AriaLabel>
                        <AriaInput className={styles.translucentInputField} />
                        <AriaFieldError className={styles.fieldError} />
                    </AriaTextField>
                    <AriaTextField
                        name="lastName"
                        value={form.lastName}
                        onChange={v => handleFormChange(v, "lastName")}
                        isRequired={required("last_name")}
                        className={styles.inputArea}
                    >
                        <AriaLabel className={styles.fieldLabel}>{t("auth.lastName")}</AriaLabel>
                        <AriaInput className={styles.translucentInputField} />
                        <AriaFieldError className={styles.fieldError} />
                    </AriaTextField>
                    <AriaTextField
                        name="email"
                        type="email"
                        value={form.email}
                        onChange={v => handleFormChange(v, "email")}
                        isRequired
                        className={styles.inputArea}
                    >
                        <AriaLabel className={styles.fieldLabel}>{t("auth.email")}</AriaLabel>
                        <AriaInput className={styles.translucentInputField} disabled={isProfileCompletion} />
                        <AriaFieldError className={styles.fieldError} />
                    </AriaTextField>
                    {!isProfileCompletion && (
                        <AriaTextField
                            name="password"
                            type="password"
                            value={form.password}
                            onChange={v => handleFormChange(v, "password")}
                            isRequired
                            minLength={8}
                            className={styles.inputArea}
                        >
                            <AriaLabel className={styles.fieldLabel}>{t("auth.passwordMin")}</AriaLabel>
                            <AriaInput className={styles.translucentInputField} />
                            <AriaFieldError className={styles.fieldError} />
                        </AriaTextField>
                    )}
                </FormStep>
            );
        case 3:
            return (
                <FormStep
                    onNext={handleFormSubmit}
                    onPrev={() => setFormStep(2)}
                    isLastStep={true}
                    isLoading={loading}
                >
                    {isProfessional && (
                        <>
                            <AriaTextField
                                name="enterpriseName"
                                value={form.enterpriseName}
                                onChange={v => handleFormChange(v, "enterpriseName")}
                                isRequired={required("enterprise_name")}
                                className={styles.inputArea}
                            >
                                <AriaLabel className={styles.fieldLabel}>{t("auth.enterpriseName")}</AriaLabel>
                                <AriaInput className={styles.translucentInputField} />
                                <AriaFieldError className={styles.fieldError} />
                            </AriaTextField>
                            <AriaTextField
                                name="phoneNumber"
                                type="tel"
                                value={form.phoneNumber}
                                onChange={v => {
                                    const digitsOnly = v.replace(/\D/g, "");
                                    handleFormChange(digitsOnly, "phoneNumber");
                                }}
                                isRequired={required("phone_number")}
                                className={styles.inputArea}
                                validationState={form.phoneNumber && !/^\d+$/.test(form.phoneNumber) ? "invalid" : undefined}
                            >
                                <AriaLabel className={styles.fieldLabel}>{t("auth.phoneNumber")}</AriaLabel>
                                <AriaInput
                                    className={styles.translucentInputField}
                                    inputMode="numeric"
                                    pattern="[0-9]*"
                                />
                                <AriaFieldError className={styles.fieldError}>
                                    {form.phoneNumber && !/^\d+$/.test(form.phoneNumber) ? t("auth.phoneNumberError") : null}
                                </AriaFieldError>
                            </AriaTextField>
                        </>
                    )}
                    <div className={styles.inputArea}>
                        <AriaLabel className={styles.fieldLabel}>{t("auth.country")}</AriaLabel>
                        <StyledSelect
                            placeholder={t("auth.country")}
                            options={countryOptions}
                            value={form.country}
                            onChange={value => handleFormChange(value, "country")}
                        />
                    </div>
                    <AriaTextField
                        name="profession"
                        value={form.profession}
                        onChange={v => handleFormChange(v, "profession")}
                        isRequired={required("profession")}
                        className={styles.inputArea}
                    >
                        <AriaLabel className={styles.fieldLabel}>{t("auth.profession")}</AriaLabel>
                        <AriaInput className={styles.translucentInputField} />
                    </AriaTextField>
                    <div className={styles.inputArea}>
                        <AriaLabel className={styles.fieldLabel}>{t("auth.educationLevel")}</AriaLabel>
                        <StyledSelect
                            placeholder={t("auth.educationLevel")}
                            options={educationLevels}
                            value={form.education}
                            onChange={value => handleFormChange(value, "education")}
                        />
                    </div>
                    <Checkbox
                        isSelected={form.acceptCGU}
                        onChange={v => handleFormChange(v, "acceptCGU")}
                        isRequired={required("accept_cgu")}
                        className={styles.checkboxInput}
                        isInvalid={required("accept_cgu") && !form.acceptCGU}
                        errorMessage={required("accept_cgu") && !form.acceptCGU ? t("auth.acceptCGU") + " " + t("auth.fixValidation") : undefined}
                    >
                        <Trans i18nKey="auth.acceptCGU" components={{ a: <a className={styles.externalLink} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()} /> }} />
                    </Checkbox>

                    <Checkbox
                        isSelected={form.acceptPrivacy}
                        onChange={v => handleFormChange(v, "acceptPrivacy")}
                        isRequired={required("accept_privacy")}
                        className={styles.checkboxInput}
                        isInvalid={required("accept_privacy") && !form.acceptPrivacy}
                        errorMessage={required("accept_privacy") && !form.acceptPrivacy ? t("auth.acceptPrivacy") + " " + t("auth.fixValidation") : undefined}
                    >
                        <Trans i18nKey="auth.acceptPrivacy" components={{ a: <a className={styles.externalLink} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()} /> }} />
                    </Checkbox>

                    <Checkbox
                        isSelected={form.acceptCommunication}
                        onChange={v => handleFormChange(v, "acceptCommunication")}
                        className={styles.checkboxInput}
                    >
                        {t("auth.acceptCommunication")}
                    </Checkbox>
                </FormStep>
            );
        default:
            return null;
    }
}
