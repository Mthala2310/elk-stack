import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

try:
    from zoneinfo import ZoneInfo
    JAKARTA_TZ = ZoneInfo("Asia/Jakarta")
except Exception:
    JAKARTA_TZ = timezone(timedelta(hours=7))

from app.ai.system_prompt import SYSTEM_PROMPT
from app.ai.tool_definitions import OPENROUTER_TOOLS
from app.ai.tool_executor import execute_tool
from app.services.openrouter_client import openrouter_chat
from app.tools.validators import validate_index_pattern

MAX_TOOL_ROUNDS = 4


def extract_date_from_index(index_name: str) -> dict[str, str] | None:
    """Mendeteksi pola tanggal YYYY.MM.DD atau YYYY-MM-DD atau YYYY_MM_DD dari nama index."""
    match = re.search(r"(\d{4})[._-](\d{2})[._-](\d{2})", index_name)
    if match:
        year, month, day = match.groups()
        month_names = {
            "01": "Januari",
            "02": "Februari",
            "03": "Maret",
            "04": "April",
            "05": "Mei",
            "06": "Juni",
            "07": "Juli",
            "08": "Agustus",
            "09": "September",
            "10": "Oktober",
            "11": "November",
            "12": "Desember",
        }
        return {
            "iso_date": f"{year}-{month}-{day}",
            "year": year,
            "month": month,
            "day": day,
            "human_date": f"{int(day)} {month_names.get(month, month)} {year}",
        }
    return None


def run_ai_chat(
    user_message: str,
    index_context: str | None = None,
) -> dict[str, Any]:
    # Validasi index agar tetap mengikuti
    # allowlist Elasticsearch Phase 5.
    if index_context is not None:
        validate_index_pattern(index_context)

    # Dapatkan waktu sistem saat ini (WIB / UTC+7)
    now_wib = datetime.now(JAKARTA_TZ)
    current_time_str = now_wib.strftime("%Y-%m-%d %H:%M:%S WIB")

    # Berikan konteks waktu dan index aktif ke LLM.
    system_content = SYSTEM_PROMPT
    system_content += f"""

=======================================================
WAKTU SISTEM SAAT INI (WIB / UTC+7)
=======================================================
Waktu sekarang: {current_time_str}
"""

    if index_context is not None:
        date_info = extract_date_from_index(index_context)
        if date_info:
            system_content += f"""
=======================================================
ACTIVE INDEX & DATE CONTEXT
=======================================================
- Index yang dipilih pengguna: {index_context}
- Tanggal terdeteksi dari nama index: {date_info['iso_date']} ({date_info['human_date']})
  * Tahun: {date_info['year']}
  * Bulan: {date_info['month']}
  * Tanggal: {date_info['day']}

PANDUAN WAKTU DARI ACTIVE INDEX INI:
1. Index ini adalah index log harian spesifik untuk tanggal {date_info['iso_date']}.
2. Anda SUDAH MEMILIKI informasi tanggal, bulan, dan tahun dari active index tersebut.
3. JANGAN PERNAH menanyakan konfirmasi tanggal kepada pengguna jika pengguna hanya menyebutkan jam (misalnya "jam 10 - 11 wib", "pukul 14.00", "antara jam 08:00 sampai 09:00").
4. Jika pengguna hanya menyebutkan rentang jam atau waktu tanpa menyebut tanggal, LANGSUNG kombinasikan jam tersebut dengan tanggal {date_info['iso_date']} (offset +07:00):
   Contoh:
   - Pertanyaan pengguna: "cek error 500 atau lebih di jam 10 - 11 wib"
   - Parameter tool: start="{date_info['iso_date']}T10:00:00+07:00", end="{date_info['iso_date']}T11:00:00+07:00"
   - Langsung panggil tool yang relevan (get_log_summary / search_logs / get_top_error_paths) sekarang juga.
5. Jika pengguna menanyakan analisis umum tanpa menyebut rentang jam (misalnya "ringkasan log", "ada error berapa", "analisis index ini"):
   Gunakan satu hari penuh untuk tanggal {date_info['iso_date']}:
   start="{date_info['iso_date']}T00:00:00+07:00", end="{date_info['iso_date']}T23:59:59+07:00"
6. JANGAN meminta konfirmasi tanggal. LANGSUNG eksekusi tool terkait dan berikan jawaban berdasarkan evidence yang diperoleh.
"""
        else:
            system_content += f"""
=======================================================
ACTIVE INDEX CONTEXT
=======================================================
Index yang dipilih pengguna: {index_context}
Gunakan index ini untuk pertanyaan saat ini.
Jika pesan tidak menyebut index lagi, gunakan active index tersebut.
Jangan memilih index lain secara otomatis.
Jangan menggunakan index di luar allowlist.
"""

    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": system_content,
        },
        {
            "role": "user",
            "content": user_message,
        },
    ]

    tool_trace: list[dict[str, Any]] = []

    for round_idx in range(MAX_TOOL_ROUNDS):
        result = openrouter_chat(
            messages=messages,
            tools=OPENROUTER_TOOLS,
            tool_choice="auto",
        )

        choice = result["choices"][0]
        message = choice["message"]
        tool_calls = message.get("tool_calls", [])

        # Jika LLM tidak memanggil tool lagi, kembalikan jawaban final
        if not tool_calls:
            return {
                "answer": message.get("content", ""),
                "active_index": index_context,
                "tool_trace": tool_trace,
                "rounds": round_idx + 1,
            }

        # Simpan pesan assistant ke riwayat sebelum memasukkan tool result
        messages.append(message)

        for tool_call in tool_calls:
            tool_call_id = tool_call.get("id")
            function = tool_call.get("function", {})
            tool_name = function.get("name")
            raw_arguments = function.get("arguments", "{}")

            try:
                if isinstance(raw_arguments, str):
                    arguments = json.loads(raw_arguments)
                else:
                    arguments = raw_arguments or {}
                is_json_valid = True
            except Exception:
                arguments = {}
                is_json_valid = False

            if not is_json_valid:
                arguments = {}
                evidence = {
                    "ok": False,
                    "error": (
                        "Tool arguments bukan "
                        "JSON yang valid."
                    ),
                }
            else:
                try:
                    # Pastikan tool menggunakan index aktif
                    if index_context is not None:
                        arguments["index"] = index_context

                    # -------------------------
                    # Jalankan TOOL ASLI
                    # -------------------------
                    tool_result = execute_tool(
                        tool_name=tool_name,
                        arguments=arguments,
                    )
                    evidence = {
                        "ok": True,
                        "data": tool_result,
                    }
                except Exception as exc:
                    # Jangan langsung matikan
                    # seluruh chat.
                    #
                    # Kirim kegagalan tool
                    # kembali ke LLM supaya
                    # LLM bisa menjelaskan
                    # limitation.
                    evidence = {
                        "ok": False,
                        "error": str(exc),
                    }

            # ---------------------------------
            # Trace untuk development/debug
            # ---------------------------------
            tool_trace.append(
                {
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "success": evidence["ok"],
                    "evidence": evidence,
                }
            )

            # ---------------------------------
            # Kirim evidence kembali
            # ke LLM sebagai role=tool
            # ---------------------------------
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": json.dumps(
                        evidence,
                        ensure_ascii=False,
                        default=str,
                    ),
                }
            )

    # Jika sudah mencapai batas ronde dan belum ada jawaban final,
    # panggil satu kali lagi tanpa tools untuk menyimpulkan
    final_result = openrouter_chat(
        messages=messages,
    )
    final_message = final_result["choices"][0]["message"]

    return {
        "answer": final_message.get("content", ""),
        "active_index": index_context,
        "tool_trace": tool_trace,
        "rounds": MAX_TOOL_ROUNDS,
    }
