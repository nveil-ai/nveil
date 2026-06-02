// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-FileContributor: Guillaume Franque
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../Auth/AuthContext';
import SEO from '../Components/SEO';
import styles from './DashboardList.module.css';
import { MdDashboard, MdAdd, MdOpenInNew, MdGridView, MdDelete, MdEdit, MdCheck, MdClose } from 'react-icons/md';
import { Button as AriaButton } from 'react-aria-components';

export default function DashboardList() {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const { secureRequest, isAuthenticated, isGuest, loading: authLoading } = useAuth();
    const [dashboards, setDashboards] = useState([]);
    const [loading, setLoading] = useState(true);
    const [creating, setCreating] = useState(false);
    const [deletingId, setDeletingId] = useState(null);
    const [confirmDeleteId, setConfirmDeleteId] = useState(null);
    const [editingId, setEditingId] = useState(null);
    const [editName, setEditName] = useState('');
    const [deleteError, setDeleteError] = useState(null);
    const editInputRef = useRef(null);

    useEffect(() => {
        if (!authLoading && !isAuthenticated) navigate('/');
    }, [authLoading, isAuthenticated, navigate]);

    const fetchDashboards = useCallback(async () => {
        if (!isAuthenticated) {
            setLoading(false);
            return;
        }
        try {
            const res = await secureRequest('/server/dashboards/list');
            if (res.ok) {
                const data = await res.json();
                setDashboards(data);
            }
        } catch (e) {
            console.error('Failed to fetch dashboards:', e);
        }
        setLoading(false);
    }, [isAuthenticated, secureRequest]);

    useEffect(() => {
        fetchDashboards();
    }, [fetchDashboards]);

    useEffect(() => {
        if (editingId && editInputRef.current) {
            editInputRef.current.focus();
            editInputRef.current.select();
        }
    }, [editingId]);

    const handleCreate = async () => {
        if (creating || isGuest) return;
        setCreating(true);
        try {
            const res = await secureRequest('/server/dashboards/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
            });
            if (res.ok) {
                await fetchDashboards();
            }
        } catch (e) {
            console.error('Failed to create dashboard:', e);
        }
        setCreating(false);
    };

    const handleDelete = async (id) => {
        if (deletingId) return;
        setDeletingId(id);
        setDeleteError(null);
        try {
            const res = await secureRequest(`/server/dashboards/${id}`, { method: 'DELETE' });
            if (res.ok) {
                setDashboards(prev => prev.filter(d => d.id !== id));
            } else {
                setDeleteError(id);
                setTimeout(() => setDeleteError(null), 3000);
            }
        } catch (e) {
            console.error('Failed to delete dashboard:', e);
            setDeleteError(id);
            setTimeout(() => setDeleteError(null), 3000);
        }
        setDeletingId(null);
        setConfirmDeleteId(null);
    };

    const startEditing = (d) => {
        setEditingId(d.id);
        setEditName(d.name || '');
    };

    const cancelEditing = () => {
        setEditingId(null);
        setEditName('');
    };

    const handleRename = async (id) => {
        const trimmed = editName.trim();
        if (!trimmed) {
            cancelEditing();
            return;
        }
        try {
            const res = await secureRequest(`/server/dashboards/${id}/rename`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: trimmed }),
            });
            if (res.ok) {
                setDashboards(prev => prev.map(d => d.id === id ? { ...d, name: trimmed } : d));
            }
        } catch (e) {
            console.error('Failed to rename dashboard:', e);
        }
        cancelEditing();
    };

    const handleEditKeyDown = (e, id) => {
        e.stopPropagation();
        if (e.key === 'Enter') handleRename(id);
        if (e.key === 'Escape') cancelEditing();
    };

    const formatDate = (iso) => {
        if (!iso) return '—';
        const d = new Date(iso);
        return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
    };

    const formatTime = (iso) => {
        if (!iso) return '';
        const d = new Date(iso);
        const now = new Date();
        const diffMs = now - d;
        const diffMin = Math.floor(diffMs / 60000);
        if (diffMin < 1) return t('dashboard.justNow');
        if (diffMin < 60) return t('dashboard.minutesAgo', { count: diffMin });
        const diffHours = Math.floor(diffMin / 60);
        if (diffHours < 24) return t('dashboard.hoursAgo', { count: diffHours });
        const diffDays = Math.floor(diffHours / 24);
        return t('dashboard.daysAgo', { count: diffDays });
    };

    const dashboardName = (d, i) => d.name || `Dashboard ${i + 1}`;

    return (
        <>
            <SEO
                title={t('seo.dashboardTitle')}
                description={t('seo.dashboardDescription')}
            />
            <main className={styles.page}>
                <div className={styles.backdrop}>
                    <div className={styles.header}>
                        <div className={styles.headerLeft}>
                            <MdDashboard className={styles.headerIcon} />
                            <h1 className={styles.title}>{t('dashboard.title')}</h1>
                        </div>
                        <AriaButton
                            className={styles.createBtn}
                            onPress={handleCreate}
                            isDisabled={creating || isGuest}
                            data-tooltip={isGuest ? t('guest.signUpForDashboards', 'Sign up to create dashboards') : undefined}
                        >
                            <MdAdd />
                            <span>{creating ? t('dashboard.creating') : t('dashboard.create')}</span>
                        </AriaButton>
                    </div>

                    {loading ? (
                        <div className={styles.loadingState}>
                            <div className={styles.loadingPulse} />
                            <div className={styles.loadingPulse} />
                            <div className={styles.loadingPulse} />
                        </div>
                    ) : dashboards.length === 0 ? (
                        <div className={styles.emptyState}>
                            <div className={styles.emptyIcon}>
                                <MdGridView />
                            </div>
                            <p className={styles.emptyTitle}>{t('dashboard.emptyTitle')}</p>
                            <p className={styles.emptyDesc}>{t('dashboard.emptyDesc')}</p>
                        </div>
                    ) : (
                        <div className={styles.grid}>
                            {dashboards.map((d, i) => (
                                <div
                                    key={d.id}
                                    className={styles.card}
                                    style={{ animationDelay: `${i * 60}ms`, cursor: 'pointer' }}
                                    role="button"
                                    tabIndex={0}
                                    onClick={() => { if (editingId !== d.id) navigate(`/dashboard/${d.token}`); }}
                                    onKeyDown={e => {
                                        if (editingId === d.id) return;
                                        if (e.key === 'Enter' || e.key === ' ') {
                                            e.preventDefault();
                                            navigate(`/dashboard/${d.token}`);
                                        }
                                    }}
                                >
                                    <div className={styles.cardGlow} />
                                    <div className={styles.cardInner}>
                                        <div className={styles.cardHeader}>
                                            {editingId === d.id ? (
                                                <div className={styles.editRow}>
                                                    <input
                                                        ref={editInputRef}
                                                        className={styles.editInput}
                                                        value={editName}
                                                        onChange={e => setEditName(e.target.value)}
                                                        onKeyDown={e => handleEditKeyDown(e, d.id)}
                                                        maxLength={255}
                                                        placeholder={t('dashboard.namePlaceholder')}
                                                    />
                                                    <button className={styles.editAction} onClick={() => handleRename(d.id)} data-tooltip={t('dashboard.save')}>
                                                        <MdCheck />
                                                    </button>
                                                    <button className={styles.editAction} onClick={cancelEditing} data-tooltip={t('dashboard.cancel')}>
                                                        <MdClose />
                                                    </button>
                                                </div>
                                            ) : (
                                                <span className={styles.cardName}>{dashboardName(d, i)}</span>
                                            )}
                                            <div className={styles.panelBadge}>
                                                <MdGridView />
                                                <span>{d.panel_count} {d.panel_count === 1 ? t('dashboard.panel') : t('dashboard.panels')}</span>
                                            </div>
                                        </div>
                                        <div className={styles.cardBody}>
                                            <span className={styles.cardDate}>{formatDate(d.created_at)}</span>
                                            {d.last_activity && (
                                                <span className={styles.cardActivity}>{formatTime(d.last_activity)}</span>
                                            )}
                                        </div>
                                        <div className={styles.cardActions}>
                                            {!isGuest && editingId !== d.id && (
                                                <button
                                                    className={styles.actionBtn}
                                                    onClick={(e) => { e.stopPropagation(); startEditing(d); }}
                                                    data-tooltip={t('dashboard.rename')}
                                                >
                                                    <MdEdit />
                                                </button>
                                            )}
                                            {!isGuest && (confirmDeleteId === d.id ? (
                                                <div className={styles.confirmRow}>
                                                    <span className={styles.confirmText}>{t('dashboard.confirmDelete')}</span>
                                                    <button
                                                        className={`${styles.actionBtn} ${styles.confirmYes}`}
                                                        onClick={(e) => { e.stopPropagation(); handleDelete(d.id); }}
                                                        disabled={deletingId === d.id}
                                                    >
                                                        <MdCheck />
                                                    </button>
                                                    <button
                                                        className={styles.actionBtn}
                                                        onClick={(e) => { e.stopPropagation(); setConfirmDeleteId(null); }}
                                                    >
                                                        <MdClose />
                                                    </button>
                                                </div>
                                            ) : (
                                                <button
                                                    className={`${styles.actionBtn} ${styles.deleteBtn}`}
                                                    onClick={(e) => { e.stopPropagation(); setConfirmDeleteId(d.id); }}
                                                    data-tooltip={t('dashboard.delete')}
                                                >
                                                    <MdDelete />
                                                </button>
                                            ))}
                                            <button
                                                className={`${styles.actionBtn} ${styles.openBtn}`}
                                                onClick={() => navigate(`/dashboard/${d.token}`)}
                                                data-tooltip={t('dashboard.open')}
                                            >
                                                <MdOpenInNew />
                                            </button>
                                        </div>
                                        {deleteError === d.id && (
                                            <span className={styles.deleteError}>{t('dashboard.refreshError')}</span>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </main>
        </>
    );
}
