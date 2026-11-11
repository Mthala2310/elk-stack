import datetime
import os
import random
import time

CURRENCIES = ["IDR", "USD", "EUR", "SGD"]
STATUS_IDS = ["SUCCESS", "PENDING", "REJECTED", "VALIDATED"]
NAMES = ["PT Sumber Makmur", "Ahmad Fauzi", "Siti Rahmawati", "CV Berkah Jaya", "Budi Santoso"]

def get_timestamp():
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]

def emit_log(level, caller, trace_id, path, message, file_handle=None):
    ts = get_timestamp()
    log_line = f"{level} {ts} {caller} - [{trace_id}][{path}]{message}"
    print(log_line)
    if file_handle:
        file_handle.write(log_line + "\n")
        file_handle.flush()

def generate_transaction(file_handle=None, scenario="random"):
    trace_id = random.randint(1400000000, 1499999999)
    service_name = "beneficiaryValidationNotification Ver. 7"
    
    if scenario == "random":
        scenario = random.choices(["success", "slow", "error"], weights=[0.75, 0.15, 0.10])[0]

    acc_no = f"0{random.randint(100000000, 999999999)}"
    acc_nm = random.choice(NAMES)
    currency = random.choice(CURRENCIES)
    status_id = random.choice(STATUS_IDS)
    upload_date = datetime.date.today().strftime("%Y-%m-%d")

    # 1. Tahap prepareInput
    inputs = [
        ("validationStatusId", status_id),
        ("uploadDate", upload_date),
        ("accountCurrency", currency),
        ("hostAccountNo", acc_no),
        ("hostAccountNm", acc_nm)
    ]
    
    for var_name, var_val in inputs:
        emit_log(
            "DEBUG", "main.Service(prepareInput:315)",
            trace_id, service_name,
            f"Input Variable Name: {var_name} -> {var_val}",
            file_handle
        )

    # 2. Tahap Start
    init_ms = random.randint(15000, 32000)
    emit_log("DEBUG", "Performance(<init>:79)", trace_id, f"{service_name}->Start", f"Start [{init_ms} ms]", file_handle)
    emit_log("DEBUG", "Performance(close:185)", trace_id, f"{service_name}->Start", "End [0 ms]", file_handle)

    # 3. Tahap getPropertiesEmail
    emit_log("DEBUG", "Performance(<init>:79)", trace_id, f"{service_name}->getPropertiesEmail", f"Start [{init_ms} ms]", file_handle)
    
    # 4. Percabangan Skenario
    if scenario == "success":
        duration = random.randint(5, 45)
        time.sleep(0.05)
        emit_log("DEBUG", "Performance(close:185)", trace_id, f"{service_name}->getPropertiesEmail", f"End [{duration} ms]", file_handle)
        emit_log("INFO", "main.MailNotification(send:120)", trace_id, service_name, f"Notification dispatched successfully to hostAccountNo: {acc_no}", file_handle)
    
    elif scenario == "slow":
        latency = random.randint(3500, 7500)
        time.sleep(0.1)
        emit_log("WARN", "Performance(close:185)", trace_id, f"{service_name}->getPropertiesEmail", f"End [{latency} ms] - SLA threshold exceeded (>3000ms)", file_handle)
        emit_log("INFO", "main.MailNotification(send:120)", trace_id, service_name, f"Notification dispatched slowly to hostAccountNo: {acc_no}", file_handle)
        
    elif scenario == "error":
        time.sleep(0.05)
        emit_log("ERROR", "main.MailService(connect:88)", trace_id, f"{service_name}->getPropertiesEmail", "Connection refused: smtp.internal.bank:587 timeout after 5000ms", file_handle)
        emit_log("ERROR", "main.Service(execute:402)", trace_id, service_name, "Transaction terminated with status FAILED: Email dispatch exception", file_handle)

def main():
    log_dir = "logs"
    log_filepath = os.path.join(log_dir, "application.log")
    
    # Buat direktori logs/ jika belum tersedia
    os.makedirs(log_dir, exist_ok=True)
    
    print(f"[*] Generator aktif. Menulis ke: {log_filepath}")
    print("[*] Tekan Ctrl+C untuk berhenti.\n")
    
    with open(log_filepath, "a", encoding="utf-8") as f:
        try:
            while True:
                generate_transaction(file_handle=f)
                time.sleep(random.uniform(0.5, 2.0))
        except KeyboardInterrupt:
            print("\n[*] Generator dihentikan.")

if __name__ == "__main__":
    main()