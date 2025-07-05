import re
import pandas as pd
import streamlit as st
from fpdf import FPDF
from io import BytesIO

# -----------------------------
# Session State Defaults
# -----------------------------
if "topup_pin" not in st.session_state:
    st.session_state.topup_pin = "0000"
if "pin_entered" not in st.session_state:
    st.session_state.pin_entered = False

# -----------------------------
# PDF Generator Class
# -----------------------------
class PDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=10)
        self.add_page()
        self.set_font("Arial", size=10)

    def add_transaction(self, transaction):
        for key, value in transaction.items():
            self.cell(0, 10, f"{key}: {value}", ln=True)
        self.cell(0, 5, "", ln=True)

# -----------------------------
# PDF Export Function
# -----------------------------
def generate_pdf(df):
    pdf = PDF()
    for _, row in df.iterrows():
        pdf.add_transaction(row)
    pdf_output = pdf.output(dest='S').encode('latin1')
    return BytesIO(pdf_output)

# -----------------------------
# SMS Parser Function
# -----------------------------
def parse_messages(messages):
    transactions = []
    for message in messages:
        try:
            data = {}

            # Identify direction
            if "Umetuma" in message or "Umetoa" in message:
                data["Direction"] = "Sent"
            elif "Umepokea" in message or "umepokea" in message:
                data["Direction"] = "Received"
            else:
                data["Direction"] = "Unknown"

            # Transaction ID or reference
            txid = re.search(r"(Kumbukumbu|Utambulisho wa muamala):\s*([A-Z0-9]+)", message)
            data["Transaction ID"] = txid.group(2) if txid else ""

            # Amount
            amount = re.search(r"Tsh\s?([\d,]+)", message)
            data["Amount"] = int(amount.group(1).replace(",", "")) if amount else 0

            # Receiver or sender
            receiver = re.search(r"kwa\s([A-Z ]+)\s?\(", message)
            data["Counterparty"] = receiver.group(1).strip().title() if receiver else ""

            # Phone number
            phone = re.search(r"\((0\d{9})\)", message)
            data["Phone"] = phone.group(1) if phone else ""

            # Commission
            comm = re.search(r"umepata\s?Tsh\s?([\d,]+)", message)
            data["Commission"] = int(comm.group(1).replace(",", "")) if comm else 0

            # Fees
            fee = re.search(r"Ada\sTsh\s([\d,]+)", message)
            data["Fee"] = int(fee.group(1).replace(",", "")) if fee else 0

            govt = re.search(r"Serikali\sTsh\s([\d,]+)", message)
            data["Govt Fee"] = int(govt.group(1).replace(",", "")) if govt else 0

            # Date & Time
            dt = re.search(r"(\d{2}/\d{2}/\d{4}\s\d{2}:\d{2})", message)
            data["Datetime"] = dt.group(1) if dt else ""

            # Balance
            bal = re.search(r"Salio[:]?[\s]*Tsh\s([\d,]+)", message)
            data["Remaining Balance"] = int(bal.group(1).replace(",", "")) if bal else 0

            # Operator guess
            if "Halopesa" in message:
                data["Operator"] = "Halopesa"
            elif "Tigo" in message:
                data["Operator"] = "Tigo Pesa"
            elif "M-Pesa" in message or "Vodacom" in message:
                data["Operator"] = "M-Pesa"
            elif "Airtel Money" in message:
                data["Operator"] = "Airtel Money"
            elif "T-Pesa" in message or "TTCL" in message:
                data["Operator"] = "T-Pesa"
            else:
                data["Operator"] = "Unknown"

            # Type guess
            if "lipa" in message.lower() or "malipo" in message.lower():
                data["Transaction Type"] = "Bill Payment"
            elif "kutoka kwa" in message.lower() or "umepokea" in message.lower():
                data["Transaction Type"] = "Deposit"
            elif "kwa" in message.lower() and data["Direction"] == "Sent":
                data["Transaction Type"] = "Withdrawal"
            else:
                data["Transaction Type"] = "Unknown"

            transactions.append(data)

        except Exception as e:
            st.warning(f"? Ujumbe haukusomeka: {e}")
    return pd.DataFrame(transactions)

# -----------------------------
# Streamlit App
# -----------------------------
st.title("?? Mchambuzi wa Miamala ya Wakala")

st.markdown("Pakia faili moja au zaidi zenye ujumbe wa miamala (plain text, kila ujumbe mstari mmoja):")
uploaded_files = st.file_uploader("Chagua Mafaili ya Maneno (txt)", type=["txt"], accept_multiple_files=True)

all_messages = []
if uploaded_files:
    for uploaded_file in uploaded_files:
        try:
            file_messages = uploaded_file.read().decode("utf-8").splitlines()
            all_messages.extend(file_messages)
        except Exception as e:
            st.warning(f"? Hitilafu kusoma faili: {uploaded_file.name} - {e}")

    df = parse_messages(all_messages)

    if not df.empty:
        # Sidebar filters
        st.sidebar.header("?? Chuja Miamala")
        counter_filter = st.sidebar.multiselect("Chagua Mpokeaji/Mtuma", options=df["Counterparty"].dropna().unique())
        if counter_filter:
            df = df[df["Counterparty"].isin(counter_filter)]

        type_filter = st.sidebar.multiselect("Aina ya Muamala", options=df["Transaction Type"].unique())
        if type_filter:
            df = df[df["Transaction Type"].isin(type_filter)]

        min_amount = st.sidebar.number_input("Kiasi cha Chini (Tsh)", min_value=0, value=0)
        df = df[df["Amount"] >= min_amount]

        # Summary Section
        st.subheader("?? Muhtasari wa Miamala")

        total_sent = df[df["Direction"] == "Sent"]["Amount"].sum()
        total_received = df[df["Direction"] == "Received"]["Amount"].sum()
        total_commission = df["Commission"].sum()

        st.markdown("**?? Ongeza Fedha (Wakala ameongeza fedha kutoka mfukoni)**")
        if not st.session_state.pin_entered:
            input_pin = st.text_input("Ingiza PIN (Chaguo la mwanzo ni 0000)", type="password")
            if input_pin == st.session_state.topup_pin:
                st.session_state.pin_entered = True
                st.success("? Umefanikiwa kufungua sehemu ya kuongeza fedha.")
            elif input_pin:
                st.error("? PIN si sahihi.")

        manual_topup = 0
        if st.session_state.pin_entered:
            manual_topup = st.number_input("?? Ingiza kiasi cha fedha ya ziada", min_value=0, value=0)
            if st.button("?? Badilisha PIN"):
                new_pin = st.text_input("Weka PIN mpya", type="password", key="new_pin")
                confirm_pin = st.text_input("Thibitisha PIN mpya", type="password", key="confirm_pin")
                if new_pin and confirm_pin and new_pin == confirm_pin:
                    st.session_state.topup_pin = new_pin
                    st.success("? PIN imebadilishwa.")
                elif new_pin and confirm_pin:
                    st.error("? PIN hazifanani.")

        cash_in_hand = total_sent - total_received + manual_topup

        latest_balances = df.sort_values("Datetime").dropna(subset=["Datetime"])
        balances = {}
        for provider in ["Halopesa", "Tigo Pesa", "M-Pesa", "Airtel Money", "T-Pesa"]:
            last = latest_balances[latest_balances["Operator"] == provider]
            if not last.empty:
                balances[provider] = last.iloc[-1]["Remaining Balance"]
            else:
                balances[provider] = "Hakuna data"

        st.markdown(f"""
        **?? Cash in Hand:** Tsh {cash_in_hand:,}  
        **?? Jumla ya Kamisheni:** Tsh {total_commission:,}  
        """)

        st.markdown("**?? Salio kwa Kila Mtandao:**")
        for op, bal in balances.items():
            st.markdown(f"- {op}: Tsh {bal:,}" if isinstance(bal, int) else f"- {op}: {bal}")

        # Data table
        st.subheader("?? Miamala Iliyogunduliwa")
        st.dataframe(df)

        # Download buttons
        st.subheader("?? Pakua Ripoti")
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("? Pakua CSV", data=csv, file_name="miamala.csv", mime="text/csv")

        pdf_data = generate_pdf(df)
        st.download_button("? Pakua PDF", data=pdf_data, file_name="miamala.pdf", mime="application/pdf")

    else:
        st.warning("? Hakuna miamala iliyopatikana kutoka kwenye mafaili.")
else:
    st.info("?? Tafadhali pakia faili moja au zaidi za maandishi.")


