// SPDX-FileCopyrightText: 2025 NVEIL SAS
// SPDX-FileContributor: Guillaume Franque
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import styles from "./NavBar.module.css";
import nveilLogo from "./nveilLogo.webp";
import nveilLogoSquare from "./nveilLogoSquare.webp";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from 'react-i18next';
import { useState, useRef, useEffect, lazy, Suspense } from 'react';

// import Auth from "../Auth/Auth";
// import WelcomeModal from "../Components/WelcomeModal";
// import ConfirmModal from "../Components/ConfirmModal";
const Auth = lazy(() => import("../Auth/Auth"));
const WelcomeModal = lazy(() => import("../Components/WelcomeModal"));
const ConfirmModal = lazy(() => import("../Components/ConfirmModal"));
import { useAuth } from "../Auth/AuthContext";
import { useRoom } from "../Room/RoomContext";
import { MdChat, MdAdd, MdDelete, MdExpandMore, MdDashboard } from "react-icons/md";
import { FaFolder, FaFolderOpen } from "react-icons/fa";
import { RiChatHistoryFill } from "react-icons/ri";
import { IoHelpCircle } from "react-icons/io5";
import { IoIosLogIn } from "react-icons/io";
import { IoIosLogOut } from "react-icons/io";
import { TbLayoutSidebarLeftCollapseFilled, TbLayoutSidebarRightCollapseFilled } from "react-icons/tb";
import { RiUserSettingsLine } from "react-icons/ri";
import { IoTelescope } from "react-icons/io5";
import { VscFeedback } from "react-icons/vsc";
import { FaCrown } from "react-icons/fa6";
import { FaDiscord } from "react-icons/fa";
import { hasBilling } from '../extensions';



import { Dialog, DialogTrigger, Modal, Heading, Button as AriaButton, ListBox, ListBoxItem, Popover } from 'react-aria-components';
/**
 * NavBar component provides the main navigation bar for the application.
 * 
 * Features:
 * - Displays navigation links based on authentication status.
 * - Allows authenticated users to upload CSV files via file input or drag-and-drop.
 * - Handles file validation (type and size) and uploads CSV files to the backend.
 * - Shows a drag-and-drop overlay when a file is being dragged over the window.
 * - Displays authentication modal for sign-in.
 * - Provides logout functionality with confirmation.
 * 
 * Hooks:
 * - Uses `useLocation` to determine the current route for active link highlighting.
 * - Uses `useAuth` for authentication state and secure requests.
 * - Uses `useState` and `useEffect` for UI state management and event listeners.
 * 
 * @component
 * @returns {JSX.Element} The rendered navigation bar component.
 */
export default function NavBar() {
	const { t, i18n } = useTranslation();

	const location = useLocation();
	const { user, logout, isAuthenticated, isGuest, secureRequest, showAuthModal: showAuth, setShowAuthModal: setShowAuth } = useAuth();
	const { rooms, currentRoom, switching, createRoom, switchRoom, deleteRoom, getRoomTitle } = useRoom();
	const navigate = useNavigate();
	const [showWelcome, setShowWelcome] = useState(false);
	const [deleteConfirm, setDeleteConfirm] = useState(null);

	const [isExpanded, setIsExpanded] = useState(() => {
		const saved = localStorage.getItem('navBarExpanded');
		return saved !== null ? JSON.parse(saved) : true;
	});

	useEffect(() => {
		localStorage.setItem('navBarExpanded', JSON.stringify(isExpanded));
	}, [isExpanded]);

	useEffect(() => {
		if (isGuest) {
			setShowWelcome(true);
		}
	}, [isGuest]);

	const getNavItemClass = (path, prefix = false) => {
		const isActive = prefix
			? location.pathname.startsWith(path)
			: location.pathname === path;
		return `${styles.navbarItem} ${isActive ? styles.active : ''}`;
	};

	const isChatActive = location.pathname === '/' || location.pathname.startsWith('/room/');
	const isDashboardActive = location.pathname === '/dashboards' || location.pathname.startsWith('/dashboard/');

	const handleLogout = async () => {
		await logout();
	};

	const handleLoginSuccess = () => {
		setShowAuth(false);
		// setShowWelcome(true);
	};

	const handleCreateRoom = async () => {
		if (isAuthenticated) {
			await createRoom();
		}
		else {
			if (window.location.pathname !== "/") {
				navigate("/");
			}
		}
	};

	const handleSwitchRoom = async (token) => {
		if (switching) return;
		await switchRoom(token);
	};

	const handleDeleteRoom = (e, roomId) => {
		e.stopPropagation();
		setDeleteConfirm(roomId);
	};

	const RoomListContent = () => (
		<div className={styles.roomListWrapper} style={{ width: '100%', padding: '0px 0px 10px 0px' }}>

			{isExpanded ? null : (
				<div className={styles.roomListHeader} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0 10px 5px 10px' }}>
					<span style={{ fontSize: '0.8rem', color: '#888' }}>{t("nav.rooms")}</span>
					<button
						onClick={handleCreateRoom}
						style={{ background: 'none', border: 'none', color: 'white', cursor: 'pointer', padding: '5px' }}
						data-tooltip={t("nav.newRoom")}
					>
						<MdAdd />
					</button>
				</div>)}
			<ListBox
				aria-label={t("nav.rooms")}
				onAction={(key) => {
					if (!key) return;
					handleSwitchRoom(key);
				}}
				className={styles.roomList}
				style={{ display: 'flex', flexDirection: 'column', gap: '2px', width: '100%', maxHeight: '300px', overflowY: 'auto' }}
			>
				{rooms.map(room => (
					<ListBoxItem
						key={room.token}
						id={room.token}
						textValue={getRoomTitle(room)}
						className={`${styles.roomItem} ${room.token === currentRoom?.token ? styles.active : ''}`}
						style={{
							display: 'flex',
							justifyContent: 'space-between',
							alignItems: 'center',
							padding: '8px 10px',
							cursor: 'pointer',
							borderRadius: '5px',
							backgroundColor: room.token === currentRoom?.token ? 'rgba(255, 255, 255, 0.1)' : 'transparent',
							color: 'white',
							outline: 'none'
						}}
					>
						<div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden', flex: 1 }}>
							<span className={styles.roomItemTitle} style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontSize: '0.9rem' }}>{getRoomTitle(room)}</span>
							{room.token === currentRoom?.token && <span className={styles.vizIndicator} style={{ color: '#00ffc2', fontSize: '0.6rem' }}>●</span>}
						</div>
						{room.token === currentRoom?.token && !isGuest && (
							<button
								className={styles.roomDeleteButton}
								onClick={(e) => handleDeleteRoom(e, room.id)}
								data-tooltip={t('nav.deleteRoom')}
								style={{ background: 'none', border: 'none', color: '#666', cursor: 'pointer' }}
							>
								<MdDelete />
							</button>
						)}
					</ListBoxItem>
				))}
			</ListBox>
		</div>
	);


	return (
		<>
			<nav className={`${styles.navbar} ${isExpanded ? styles.navbarExpanded : ''}`}>
				<div className={styles.navbarStart}>

					<div className={styles.navbarBrand} id="nav-logo">
						<a href="https://www.nveil.com" target="_blank" rel="noopener noreferrer">
							<img src={isExpanded ? nveilLogo : nveilLogoSquare} alt="Nveil Logo" className={styles.navbarLogo} width={isExpanded ? 96 : 38} height={isExpanded ? 44 : 38} />
						</a>
					</div>
					<div className={styles.navbarMenu}>
						<button
							onClick={() => setIsExpanded(!isExpanded)}
							className={styles.navbarItem}
							style={{ background: 'none', border: 'none', cursor: 'pointer' }}
						>
							{isExpanded ? <TbLayoutSidebarLeftCollapseFilled /> : <TbLayoutSidebarRightCollapseFilled />}
							<div className={styles.textOnNavHovered}>{isExpanded ? t("nav.collapse") : t("nav.expand")}</div>
						</button>
						{/* Room List - only show when authenticated (including guests) */}
						{isAuthenticated && (
							isExpanded ? (
								<div style={{ display: 'flex', flexDirection: 'column' }}>
									<span className={`${styles.navbarItem} ${isChatActive ? styles.active : ''}`} style={{ justifyContent: 'space-between' }}>
										<span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
											<MdChat />
											<div className={styles.textOnNavHovered}>{t("nav.rooms")}</div>
										</span>
										<button
											onClick={handleCreateRoom}
											style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', padding: '2px 4px', display: 'flex', alignItems: 'center' }}
											data-tooltip={t("nav.newRoom")}
											disabled={isGuest}
										>
											<MdAdd />
										</button>
									</span>
									<RoomListContent />
								</div>
							) : (
								<DialogTrigger>
									<AriaButton className={`${styles.navbarItem} ${isChatActive ? styles.active : ''}`} style={{ border: 'none', cursor: 'pointer' }}>
										<MdChat />
										<div className={styles.textOnNavHovered}>{t("nav.rooms")}</div>
									</AriaButton>
									<Popover placement="right top" offset={20} style={{ background: '#1e1e1e', border: '1px solid #333', borderRadius: '8px', padding: '10px', width: '250px', boxShadow: '0 4px 12px rgba(0,0,0,0.5)' }}>
										<Dialog style={{ outline: 'none' }}>
											<RoomListContent />
										</Dialog>
									</Popover>
								</DialogTrigger>
							)
						)}

						{isAuthenticated && (
							<Link to="/dashboards" className={`${styles.navbarItem} ${isDashboardActive ? styles.active : ''}`} id="nav-dashboards"><MdDashboard /><div className={styles.textOnNavHovered}>{t("nav.dashboards")}</div></Link>
						)}
						{isAuthenticated && !isGuest && (
							<Link to="/data" className={getNavItemClass('/data')} id="nav-data">{location.pathname === '/data' ? <FaFolderOpen /> : <FaFolder />}<div className={styles.textOnNavHovered}>{t("nav.data")}</div></Link>
						)}
						<Link to="/explore" className={getNavItemClass('/explore')} id="nav-explore"><IoTelescope /><div className={styles.textOnNavHovered}>{t("nav.explore")}</div></Link>
						{/* {isAuthenticated && (
							<label className={`${styles.navbarItem} ${styles.csvLabel}`}>
								<IoIosCloudUpload /><div className={styles.textOnNavHovered}>{t("nav.upload")}</div>
								<input
									ref={fileInputRef}
									className={styles.csvUpload}
									type="file"
									id="file-upload"
									accept={allowedExtensions.join(",")}
									multiple
									onChange={handleFileUpload}
								/>
							</label>
						)} */}
					</div>
				</div>
				<div className={styles.navbarEnd}>
					{/* Settings - hide for guests */}
					{hasBilling() && (
						<Link to="/plan" className={getNavItemClass('/plan')} id="nav-plan">
							<div style={{ position: 'relative', display: 'flex' }}>
								<FaCrown />
								<div className={styles.notificationPill}></div>
							</div>
							<div className={styles.textOnNavHovered}>{t("nav.plan")}</div>
						</Link>
					)}
					{isAuthenticated && !isGuest && (
						<>
							<Link to="/settings" className={getNavItemClass('/settings')} id="nav-settings"><RiUserSettingsLine /><div className={styles.textOnNavHovered}>{t("nav.settings")}</div></Link>
						</>
					)}
					<div className={styles.compactRow}>
						<a href="https://discord.gg/3KdDwzT7rt" target="_blank" rel="noopener noreferrer" className={`${styles.navbarItem} ${styles.compactItem}`} id="nav-discord" aria-label="Discord">
							<FaDiscord />
							<div className={styles.compactLabel}>Discord</div>
						</a>
						<Link to="/feedback" className={`${getNavItemClass('/feedback')} ${styles.compactItem}`} id="nav-feedback" aria-label={t("nav.feedback")}>
							<VscFeedback />
							<div className={styles.compactLabel}>{t("nav.feedback")}</div>
						</Link>
					</div>
					{/* <Link to="/help" className={getNavItemClass('/help')}><IoHelpCircle /><div className={styles.textOnNavHovered}>{t("help")}</div></Link> */}
					{/* Show login for unauthenticated users AND guests */}
					{isAuthenticated && !isGuest ? (
						<>
							<DialogTrigger>
								<AriaButton className={getNavItemClass('/logout') + styles.logButton} id="nav-logout"><IoIosLogOut /><div className={styles.textOnNavHovered}>{t("nav.logout")}</div></AriaButton>
								<Modal className={styles.modal}>
									<Dialog role="alertdialog" className={styles.dialog}>
										{({ close }) => (
											<>
												<Heading style={{ fontSize: 24 }}>{t('nav.logoutConfirmationTitle')}</Heading>
												<p>{t('nav.logoutConfirmation')} {user.email}?</p>
												<div style={{ display: "flex", marginTop: 45, flexDirection: "column-reverse" }}>
													<AriaButton slot="close"
														className={"defaultButton"}
														autoFocus
													>
														{t('cancel')}
													</AriaButton>
													<AriaButton slot="close"
														onPress={() => {
															handleLogout();
														}}
														className={"defaultButton active"}
													>
														{t('nav.disconnect')}
													</AriaButton>
												</div>
											</>
										)}
									</Dialog>
								</Modal>
							</DialogTrigger>
						</>
					) : isGuest ? (
						<button onClick={() => setShowAuth(true)} className={getNavItemClass('/logout') + styles.logButton} id="nav-login"><IoIosLogIn /><div className={styles.textOnNavHovered}>{t("nav.login")}</div></button>
					) : (
						<button onClick={() => setShowAuth(true)} className={getNavItemClass('/logout') + styles.logButton} id="nav-login"><IoIosLogIn /><div className={styles.textOnNavHovered}>{t("nav.login")}</div></button>
					)}

				</div >
			</nav >

			<Suspense fallback={null}>
				{showAuth && (
					<Auth
						isOpen
						onClose={() => setShowAuth(false)}
						onLoginSuccess={handleLoginSuccess}
					/>
				)}
				{showWelcome && (
					<WelcomeModal open onClose={() => setShowWelcome(false)} />
				)}
				{deleteConfirm !== null && (
					<ConfirmModal
						isOpen
						onClose={() => setDeleteConfirm(null)}
						onConfirm={() => deleteRoom(deleteConfirm)}
						title={t('nav.deleteRoomConfirm')}
						confirmLabel={t('nav.deleteRoom')}
						cancelLabel={t('cancel')}
						variant="danger"
					/>
				)}
			</Suspense>
		</>
	);
}
