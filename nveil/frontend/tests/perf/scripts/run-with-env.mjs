#!/usr/bin/env node
// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Tiny cross-platform env-var setter + command runner.
// Used by package.json perf:headed / perf:trace scripts so shell-inline
// `HEADED=1 playwright test ...` works uniformly on bash, cmd, powershell.
//
// Usage: node run-with-env.mjs KEY1=val1 KEY2=val2 cmd arg1 arg2 ...

import { spawn } from 'node:child_process';

const args = process.argv.slice(2);
const env = { ...process.env };

// Pull leading KEY=VALUE pairs out of argv.
while (args.length && /^[A-Z_][A-Z0-9_]*=/i.test(args[0])) {
  const [k, ...rest] = args.shift().split('=');
  env[k] = rest.join('=');
}

if (args.length === 0) {
  console.error('run-with-env.mjs: no command given');
  process.exit(2);
}

const [cmd, ...cmdArgs] = args;
const child = spawn(cmd, cmdArgs, { env, stdio: 'inherit', shell: true });
child.on('exit', (code) => process.exit(code ?? 1));
