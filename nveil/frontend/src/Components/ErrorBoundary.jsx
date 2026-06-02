// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import React from 'react';

class ErrorBoundary extends React.Component {
	constructor(props) {
		super(props);
		this.state = { hasError: false, error: null };
	}

	static getDerivedStateFromError(error) {
		return { hasError: true, error };
	}

	componentDidCatch(error, errorInfo) {
		const label = this.props.fallbackMessage || 'ErrorBoundary';
		console.error(
			`%c[ErrorBoundary: ${label}] ${error?.name || 'Error'}: ${error?.message || error}`,
			'color:#ff5555;font-weight:bold',
		);
		console.error('  stack:\n', error?.stack || '(no stack)');
		console.error('  componentStack:', errorInfo?.componentStack || '(no componentStack)');
		console.error('  url:', window.location.href);
		console.error('  error object:', error);
	}

	handleRetry = () => {
		this.setState({ hasError: false, error: null });
	};

	render() {
		if (this.state.hasError) {
			return (
				<div style={{
					display: 'flex',
					flexDirection: 'column',
					justifyContent: 'center',
					alignItems: 'center',
					height: '100%',
					color: '#999',
					backgroundColor: '#1e1e1e',
					gap: '16px',
					padding: '20px',
				}}>
					<span style={{ fontSize: '1rem' }}>
						{this.props.fallbackMessage || 'Something went wrong'}
					</span>
					<button
						onClick={this.handleRetry}
						style={{
							padding: '10px 20px',
							backgroundColor: '#333',
							color: 'white',
							border: '1px solid #555',
							borderRadius: '20px',
							cursor: 'pointer',
							fontSize: '0.85rem'
						}}
					>
						Retry
					</button>
				</div>
			);
		}

		return this.props.children;
	}
}

export default ErrorBoundary;
