export async function sendAiMessage(message, index) {

  let response;

  try {
    response = await fetch("/api/ai/chat", {
      method: "POST",

      headers: {
        "Content-Type": "application/json",
      },

      body: JSON.stringify({
        message: message,
        index: index,
      }),
    });

  } catch (error) {
    throw new Error(
      "Tidak dapat terhubung ke backend FastAPI."
    );
  }

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const detail =
      typeof data.detail === "string"
        ? data.detail
        : "Terjadi kesalahan pada backend.";

    throw new Error(
      `HTTP ${response.status}: ${detail}`
    );
  }

  if (
    typeof data.answer !== "string" ||
    !data.answer.trim()
  ) {
    throw new Error(
      "Backend tidak mengembalikan jawaban AI yang valid."
    );
  }

  return {
    answer: data.answer,
    activeIndex: data.active_index ?? null,
  };
}
