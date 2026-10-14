/**
 * GhostGrid Client Authentication Controller
 */

document.addEventListener("DOMContentLoaded", () => {
  const loginBtn = document.getElementById("loginBtn");
  const logoutBtn = document.getElementById("logoutBtn");
  const guestBtn = document.getElementById("guestBtn");
  const userStatusLabel = document.getElementById("userStatusLabel");

  // Check backend session heartbeat
  async function checkSession() {
    try {
      const authHeader = await getAuthToken();
      const res = await fetch("/api/auth/me", {
        headers: { "Authorization": authHeader }
      });
      if (res.ok) {
        const data = await res.json();
        if (userStatusLabel) {
          userStatusLabel.textContent = `OPERATIVE: ${data.user.email || data.user.name}`;
        }
      }
    } catch (err) {
      console.warn("Session check fallback:", err);
    }
  }

  // Guest / Dev Login
  if (guestBtn) {
    guestBtn.addEventListener("click", () => {
      localStorage.setItem("ghostgrid_user", "Operative_Guest");
      window.location.href = "/browser";
    });
  }

  // Firebase Email/Google Login trigger
  if (loginBtn) {
    loginBtn.addEventListener("click", async () => {
      if (isDevMockMode) {
        alert("[GHOSTGRID DEV MODE] Firebase keys not configured yet. Continuing as Guest Operative.");
        window.location.href = "/browser";
        return;
      }

      const provider = new firebase.auth.GoogleAuthProvider();
      try {
        await authInstance.signInWithPopup(provider);
        window.location.href = "/browser";
      } catch (err) {
        alert("Authentication failed: " + err.message);
      }
    });
  }

  // Logout trigger
  if (logoutBtn) {
    logoutBtn.addEventListener("click", async () => {
      if (authInstance && !isDevMockMode) {
        await authInstance.signOut();
      }
      localStorage.removeItem("ghostgrid_user");
      window.location.href = "/";
    });
  }

  checkSession();
});