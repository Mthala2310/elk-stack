import { sendAiMessage } from "./ai-api.js";

export function initAiChat() {

  const form = document.querySelector("#ai-form");
  const input = document.querySelector("#ai-input");
  const messages = document.querySelector("#ai-messages");
  const sendButton = document.querySelector("#ai-send");

  const indexLabel = document.querySelector(
    "#active-index-label"
  );

  // Ambil index aktif dari sessionStorage.
  let activeIndex = sessionStorage.getItem(
    "activeLogIndex"
  ) || null;

  // --------------------------------
  // TAMPILAN ACTIVE INDEX
  // --------------------------------

  function updateIndexLabel() {
    if (!indexLabel) return;

    indexLabel.textContent = activeIndex
      ? `Index aktif: ${activeIndex}`
      : "Index aktif: belum dipilih";
  }

  updateIndexLabel();

  // --------------------------------
  // DETEKSI INDEX DARI PESAN
  // --------------------------------

  function detectIndex(question) {

    // Mengenali index seperti:
    // app-logs-*
    // app-logs-2026.10.05
    // app-logs-custom
    const matches = question.match(
      /\bapp-logs-[a-zA-Z0-9._*-]+/gi
    );

    if (!matches) {
      return null;
    }

    // Jika ada lebih dari satu, gunakan
    // penyebutan terakhir.
    return matches[matches.length - 1]
      .replace(/[.,;:!?]+$/, "");
  }

  // --------------------------------
  // MEMBUAT BUBBLE CHAT
  // --------------------------------

  function addMessage(role, content) {

    const bubble = document.createElement("div");

    bubble.classList.add("message", role);
    bubble.textContent = content;

    messages.appendChild(bubble);

    messages.scrollTop = messages.scrollHeight;

    return bubble;
  }

  // --------------------------------
  // ENTER = KIRIM
  // SHIFT + ENTER = BARIS BARU
  // --------------------------------

  input.addEventListener("keydown", (event) => {

    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.isComposing
    ) {

      event.preventDefault();

      if (!sendButton.disabled) {
        form.requestSubmit();
      }
    }
  });

  // --------------------------------
  // SUBMIT CHAT
  // --------------------------------

  form.addEventListener("submit", async (event) => {

    event.preventDefault();

    if (sendButton.disabled) return;

    const question = input.value.trim();

    if (!question) return;

    if (question.length > 4000) {
      addMessage(
        "assistant",
        "Pertanyaan maksimal 4000 karakter."
      );
      return;
    }

    // Deteksi apakah pengguna menyebut
    // index baru di dalam pesannya.
    const newIndex = detectIndex(question);

    // Jika ada index baru, prioritaskan.
    // Jika tidak, pakai index aktif.
    const selectedIndex = newIndex || activeIndex;

    // Mencegah pergantian ke index yang
    // tidak dikenali oleh parser prototype.
    const switchingIndex =
      /\b(?:ganti|ubah|pindah|gunakan|pakai)\s+(?:ke\s+)?(?:index|indeks)\b/i
        .test(question);

    if (switchingIndex && !newIndex) {
      addMessage(
        "assistant",
        "Index baru belum dikenali. Untuk prototype ini gunakan pola app-logs-* atau index app-logs-YYYY.MM.dd."
      );
      return;
    }

    if (!selectedIndex) {
      addMessage(
        "assistant",
        "Silakan sebutkan index terlebih dahulu, misalnya app-logs-*."
      );
      return;
    }

    addMessage("user", question);

    input.value = "";

    input.disabled = true;
    sendButton.disabled = true;
    sendButton.textContent = "Memproses...";

    const loadingMessage = addMessage(
      "assistant",
      "Sedang menganalisis log..."
    );

    try {

      // Kirim index yang dipilih ke backend.
      const result = await sendAiMessage(
        question,
        selectedIndex
      );

      loadingMessage.textContent = result.answer;

      // Simpan index setelah backend berhasil.
      activeIndex = result.activeIndex || selectedIndex;

      sessionStorage.setItem(
        "activeLogIndex",
        activeIndex
      );

      updateIndexLabel();

    } catch (error) {

      loadingMessage.textContent =
        `Gagal: ${error.message}`;

    } finally {

      input.disabled = false;
      sendButton.disabled = false;
      sendButton.textContent = "Kirim";

      input.focus();

      messages.scrollTop = messages.scrollHeight;
    }
  });
}
