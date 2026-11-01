// Play Store markets and review languages offered in the analysis form.

export const COUNTRIES: [code: string, name: string][] = [
  ["us", "United States"], ["gb", "United Kingdom"], ["in", "India"], ["ca", "Canada"], ["au", "Australia"],
  ["de", "Germany"], ["fr", "France"], ["es", "Spain"], ["it", "Italy"], ["nl", "Netherlands"],
  ["se", "Sweden"], ["pl", "Poland"], ["br", "Brazil"], ["mx", "Mexico"], ["ar", "Argentina"],
  ["jp", "Japan"], ["kr", "South Korea"], ["id", "Indonesia"], ["ph", "Philippines"], ["vn", "Vietnam"],
  ["th", "Thailand"], ["my", "Malaysia"], ["sg", "Singapore"], ["pk", "Pakistan"], ["bd", "Bangladesh"],
  ["ae", "United Arab Emirates"], ["sa", "Saudi Arabia"], ["tr", "Türkiye"], ["eg", "Egypt"], ["ng", "Nigeria"],
  ["ke", "Kenya"], ["za", "South Africa"], ["ie", "Ireland"], ["nz", "New Zealand"], ["pt", "Portugal"],
  ["ch", "Switzerland"], ["at", "Austria"], ["be", "Belgium"], ["dk", "Denmark"], ["no", "Norway"], ["fi", "Finland"],
];

export const LANGUAGES: [code: string, name: string][] = [
  ["en", "English"], ["hi", "Hindi"], ["es", "Spanish"], ["pt", "Portuguese"], ["fr", "French"], ["de", "German"],
  ["it", "Italian"], ["nl", "Dutch"], ["sv", "Swedish"], ["pl", "Polish"], ["tr", "Turkish"], ["ru", "Russian"],
  ["uk", "Ukrainian"], ["ar", "Arabic"], ["ja", "Japanese"], ["ko", "Korean"], ["zh", "Chinese"], ["id", "Indonesian"],
  ["vi", "Vietnamese"], ["th", "Thai"], ["ms", "Malay"], ["fil", "Filipino"], ["bn", "Bengali"], ["ta", "Tamil"],
  ["te", "Telugu"], ["mr", "Marathi"], ["ur", "Urdu"],
];

export const INSIGHT_LANGUAGES = ["English", "Spanish", "Portuguese", "French", "German", "Hindi", "Japanese"];

export const countryName = (code: string | null | undefined) =>
  COUNTRIES.find(([c]) => c === code)?.[1] ?? code?.toUpperCase() ?? "Unknown market";
