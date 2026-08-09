document.addEventListener("DOMContentLoaded", () => {
    configureRegistrationMode();
    const loginForm = document.getElementById("login-form");
    const registerForm = document.getElementById("register-form");
    if (loginForm) loginForm.addEventListener("submit", handleLogin);
    if (registerForm) registerForm.addEventListener("submit", handleRegister);
});


async function configureRegistrationMode() {
    const form = document.getElementById("register-form");
    if (!form) return;
    try {
        const response = await fetch("/api/registration-mode", {credentials:"same-origin"});
        if (!response.ok) return;
        const data = await response.json();
        const subtitle = document.querySelector(".auth-card .subtitle");
        const button = document.getElementById("submit-button");
        if (data.mode === "approval") {
            if (subtitle) subtitle.textContent = "Choisis ton pseudo et ta classe. Un admin validera ensuite ton accès.";
            if (button) button.textContent = "Envoyer ma demande";
        } else if (data.mode === "closed") {
            if (subtitle) subtitle.textContent = "Les inscriptions sont fermées pour le moment.";
            if (button) { button.disabled = true; button.textContent = "Inscriptions fermées"; }
        }
    } catch (_) {}
}

function showError(message) {
    const box = document.getElementById("error-message");
    if (!box) return;
    box.textContent = message;
    box.classList.add("visible");
}
function hideError() {
    const box = document.getElementById("error-message");
    if (box) box.classList.remove("visible");
}
function showSuccess(message) {
    const box = document.getElementById("success-message");
    if (!box) return;
    box.textContent = message;
    box.classList.add("visible");
}
function setSubmitting(isSubmitting) {
    const button = document.getElementById("submit-button");
    if (!button) return;
    if (!button.dataset.originalText) button.dataset.originalText = button.textContent;
    button.disabled = isSubmitting;
    button.textContent = isSubmitting ? "Envoi..." : button.dataset.originalText;
}

async function handleLogin(event) {
    event.preventDefault(); hideError(); setSubmitting(true);
    try {
        const response = await fetch("/api/login", {
            method: "POST", headers: {"Content-Type":"application/json"}, credentials: "same-origin",
            body: JSON.stringify({username: document.getElementById("username").value, password: document.getElementById("password").value})
        });
        if (!response.ok) {
            const data = await response.json(); showError(data.detail || "Connexion impossible."); setSubmitting(false); return;
        }
        window.location.href = "/";
    } catch (e) { showError("Impossible de contacter le serveur."); setSubmitting(false); }
}

async function handleRegister(event) {
    event.preventDefault(); hideError();
    const password = document.getElementById("password").value;
    if (password !== document.getElementById("password-confirm").value) { showError("Les mots de passe ne correspondent pas."); return; }
    setSubmitting(true);
    try {
        const response = await fetch("/api/register", {
            method: "POST", headers: {"Content-Type":"application/json"}, credentials: "same-origin",
            body: JSON.stringify({
                username: document.getElementById("username").value.trim(),
                class_code: document.getElementById("class-code").value.trim().toUpperCase(),
                password
            })
        });
        const data = await response.json();
        if (!response.ok) {
            const msg = Array.isArray(data.detail) ? data.detail.map(x => x.msg).join(" ") : data.detail;
            showError(msg || "Demande impossible."); setSubmitting(false); return;
        }
        if (data.mode === "open") {
            showSuccess("Compte créé ✅ Connexion en cours...");
            setTimeout(() => { window.location.href = "/"; }, 500);
            return;
        }
        document.getElementById("register-form").style.display = "none";
        showSuccess("Demande envoyée ✅ Un administrateur doit maintenant l'accepter avant que tu puisses te connecter.");
    } catch (e) { showError("Impossible de contacter le serveur."); setSubmitting(false); }
}
