// SPDX-FileCopyrightText: 2025 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import { Checkbox as AriaCheckbox, Label, FieldError } from 'react-aria-components';

/**
 * Custom Checkbox with SVG indicator.
 * @param {Omit<import('react-aria-components').CheckboxProps, 'children'> & { children?: React.ReactNode }} props
 */
export default function Checkbox({ children, errorMessage, ...props }) {
  return (
    <AriaCheckbox {...props}>
      {({ isIndeterminate, isInvalid }) => (
        <>
          <div className="checkbox">
            <svg viewBox="0 0 18 18" aria-hidden="true" width={18} height={18}>
              {isIndeterminate
                ? <rect x={1} y={7.5} width={15} height={3} />
                : <polyline points="1 9 7 14 15 4" fill="none" stroke="currentColor" strokeWidth={2} />}
            </svg>
          </div>
          <Label>{children}</Label>
          {isInvalid && errorMessage && (
            <FieldError>{errorMessage}</FieldError>
          )}
        </>
      )}
    </AriaCheckbox>
  );
}