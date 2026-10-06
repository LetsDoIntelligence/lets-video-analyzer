export const THEME_STORAGE_KEY = "lets-theme";

/** Runs before hydration to apply the saved theme and avoid a flash. */
export const themeInitScript = `try{var t=localStorage.getItem("${THEME_STORAGE_KEY}");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t;}catch(e){}`;
