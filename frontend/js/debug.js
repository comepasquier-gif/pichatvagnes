/**
 * debug.js
 * --------
 * Petite console de diagnostic technique intégrée à la page, pensée
 * comme un outil de développeur discret (repliable, en bas de page) —
 * pas un menu de jeu vidéo. Utile pour voir rapidement, sans ouvrir
 * les outils du navigateur (F12), ce que l'application sait de l'état
 * courant : utilisateur connecté, rôle, salon actif, état du WebSocket.
 *
 * Pour retirer ce panneau en production, il suffit de supprimer :
 * - le bloc <footer id="debug-panel"> dans index.html
 * - la balise <script src="/js/debug.js"> dans index.html
 * - ce fichier
 */

document.addEventListener("DOMContentLoaded", () => {
    const toggleButton = document.getElementById("debug-toggle");
    const content = document.getElementById("debug-content");

    // Affiche immédiatement les infos de debug au chargement, sans
    // attendre un clic (utile en phase de mise au point).
    refreshDebugInfo();

    toggleButton.addEventListener("click", () => {
        const isVisible = content.style.display !== "none";
        content.style.display = isVisible ? "none" : "block";

        if (!isVisible) {
            refreshDebugInfo();
        }
    });
});

/**
 * Récupère l'état courant de l'application et l'affiche dans le panneau.
 * Fonction volontairement simple : elle lit des variables globales déjà
 * définies par les autres scripts (app.js, websocket.js) plutôt que de
 * dupliquer leur logique.
 */
async function refreshDebugInfo() {
    const logBox = document.getElementById("debug-log");

    let meResponseText = "(non appelé)";
    let meStatusCode = "-";

    try {
        const response = await fetch("/api/me", { credentials: "same-origin" });
        meStatusCode = response.status;
        const data = await response.json();
        meResponseText = JSON.stringify(data, null, 2);
    } catch (error) {
        meResponseText = `Erreur : ${error.message}`;
    }

    const wsState = typeof chatSocket !== "undefined" && chatSocket
        ? describeWebSocketState(chatSocket.readyState)
        : "non initialisé";

    const roomId = typeof currentRoomId !== "undefined" ? currentRoomId : "non défini";

    logBox.textContent =
        `--- /api/me (HTTP ${meStatusCode}) ---\n` +
        `${meResponseText}\n\n` +
        `--- État du chat ---\n` +
        `Salon actif (currentRoomId) : ${roomId}\n` +
        `État WebSocket : ${wsState}\n\n` +
        `--- Page ---\n` +
        `URL : ${window.location.href}\n` +
        `User-Agent : ${navigator.userAgent}`;
}

/**
 * Traduit le code numérique readyState d'un WebSocket en texte lisible.
 */
function describeWebSocketState(readyState) {
    const states = {
        0: "CONNECTING (0)",
        1: "OPEN (1)",
        2: "CLOSING (2)",
        3: "CLOSED (3)",
    };
    return states[readyState] || `Inconnu (${readyState})`;
}
