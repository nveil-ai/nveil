# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

all:
	npm install
	npx puppeteer browsers install chrome
	npm run build

build:
	npm run build

install:
	npm install

prerender:
	npx puppeteer browsers install chrome
	npm run prerender

clean:
	rm -rf node_modules package-lock.json .vite
	npm cache clean --force
	npx puppeteer browsers remove chrome

fclean: clean
	rm -rf dist

re: fclean all

.PHONY: all clean fclean re build install prerender
