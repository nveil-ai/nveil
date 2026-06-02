// SPDX-FileCopyrightText: 2025 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';


import commonEn from "./Locales/en/common.json";
import commonFr from "./Locales/fr/common.json";

const RESOURCES = {
	en: { translation: commonEn },
	fr: { translation: commonFr }
};


const randomizeTranslation =(value)=> {
    return Array.isArray(value) ? value[Math.floor(Math.random() * value.length)] : value;
  }
	
//   use({
//   type: "postProcessor",
//   name: "random",
//   process: function (value, key, options, translator) {
// 	console.log(randomizeTranslation(value));
//         return randomizeTranslation(value);
//       }
// })
i18n.use(LanguageDetector).use(initReactI18next).init({
	supportedLngs: ["en", "fr"],
	debug: false,
	resources: RESOURCES,
	fallbackLng: "en"
});

i18n.randomT = function (key, values) {
	const value = i18n.t(key, { returnObjects: true });

	if (Array.isArray(value)) {
		return value[Math.floor(Math.random() * value.length)];
	} else {
		return value;
	}
}
export default i18n;