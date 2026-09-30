import streamlit as st
import pandas as pd
import sqlite3
import os
import hmac
import hashlib
from io import BytesIO
from datetime import date

st.set_page_config(page_title="MyDesk", layout="wide")

DB = "mydesk.db"
CATEGORIES = ["Food", "Transport", "Airtime", "School", "Rent", "Other"]


# ---------- Database ----------
def init_db():
    conn = sqlite3.connect(DB)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE, salt TEXT, pw_hash TEXT)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, type TEXT, category TEXT,
            description TEXT, amount REAL)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task TEXT, done INTEGER DEFAULT 0)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, name TEXT, phone TEXT)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, receipt_no INTEGER, date TEXT,
            business TEXT, customer TEXT, phone TEXT,
            items TEXT, total REAL)"""
    )
    for table, col, typ in [
        ("expenses", "user_id", "INTEGER"),
        ("todos", "user_id", "INTEGER"),
        ("users", "business", "TEXT"),
    ]:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
        if col not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
    conn.commit()
    conn.close()


def read(query, params=()):
    conn = sqlite3.connect(DB)
    try:
        return pd.read_sql_query(query, conn, params=params)
    finally:
        conn.close()


def run(query, params=()):
    conn = sqlite3.connect(DB)
    try:
        conn.execute(query, params)
        conn.commit()
    finally:
        conn.close()


# ---------- Auth ----------
def hash_pw(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), 100000
    ).hex()


def register(username, password):
    username = username.strip().lower()
    if len(username) < 3:
        return False, "Username iwe angalau herufi 3"
    if len(password) < 4:
        return False, "Password iwe angalau herufi 4"

    conn = sqlite3.connect(DB)
    try:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE username=?", (username,)
        ).fetchone()
        if exists:
            return False, "Username tayari imechukuliwa"

        first_user = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        salt = os.urandom(16).hex()
        cur = conn.execute(
            "INSERT INTO users (username, salt, pw_hash) VALUES (?,?,?)",
            (username, salt, hash_pw(password, salt)),
        )
        uid = cur.lastrowid
        if first_user:
            conn.execute("UPDATE expenses SET user_id=? WHERE user_id IS NULL", (uid,))
            conn.execute("UPDATE todos SET user_id=? WHERE user_id IS NULL", (uid,))
        conn.commit()
        return True, "Akaunti imetengenezwa! Sasa ingia (Login)."
    finally:
        conn.close()


def login(username, password):
    username = username.strip().lower()
    conn = sqlite3.connect(DB)
    try:
        row = conn.execute(
            "SELECT id, salt, pw_hash FROM users WHERE username=?", (username,)
        ).fetchone()
    finally:
        conn.close()
    if row and hmac.compare_digest(row[2], hash_pw(password, row[1])):
        return row[0], username
    return None, None


# ---------- Data ----------
def load_expenses(uid):
    df = read(
        """SELECT id, date AS Date, type AS Type, category AS Category,
                  description AS Description, amount AS Amount
           FROM expenses WHERE user_id=? ORDER BY date, id""",
        (uid,),
    )
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0)
    return df


def load_todos(uid):
    df = read(
        "SELECT id, task AS Task, done AS Done FROM todos WHERE user_id=? ORDER BY id",
        (uid,),
    )
    df["Done"] = df["Done"].astype(bool)
    return df


def load_customers(uid):
    return read(
        "SELECT id, name AS Name, phone AS Phone FROM customers WHERE user_id=? ORDER BY name",
        (uid,),
    )


def load_receipts(uid):
    return read(
        """SELECT id, receipt_no, date, business, customer, phone, items, total
           FROM receipts WHERE user_id=? ORDER BY id DESC""",
        (uid,),
    )


def get_business(uid):
    df = read("SELECT business FROM users WHERE id=?", (uid,))
    if not df.empty and df.iloc[0, 0]:
        return df.iloc[0, 0]
    return "Biashara Yangu"


def build_receipt(business, no, rdate, customer, phone, items_text, total):
    line = "-" * 32
    parts = [business.upper(), f"Risiti Na: {no:04d}", f"Tarehe: {rdate}"]
    if customer:
        parts.append(f"Mteja: {customer}")
    if phone:
        parts.append(f"Simu: {phone}")
    parts += [line, items_text, line, f"JUMLA: {total:,.0f} TSh", "Asante kwa kununua!"]
    return "\n".join(parts)


def to_excel(df):
    out = df.drop(columns="id").copy()
    out["Date"] = out["Date"].dt.date
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        out.to_excel(writer, index=False, sheet_name="Expenses")
    return buf.getvalue()


init_db()

# ---------- Login screen ----------
if "user_id" not in st.session_state:
    st.session_state.user_id = None
    st.session_state.username = None

if st.session_state.user_id is None:
    st.title("MyDesk")
    tab_login, tab_reg = st.tabs(["Login", "Jisajili"])

    with tab_login:
        with st.form("login_form"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            go = st.form_submit_button("Ingia")
        if go:
            uid_, uname = login(u, p)
            if uid_:
                st.session_state.user_id = uid_
                st.session_state.username = uname
                st.rerun()
            else:
                st.error("Username au password si sahihi")

    with tab_reg:
        with st.form("reg_form"):
            u2 = st.text_input("Username mpya")
            p2 = st.text_input("Password mpya", type="password")
            p3 = st.text_input("Rudia password", type="password")
            go2 = st.form_submit_button("Tengeneza akaunti")
        if go2:
            if p2 != p3:
                st.error("Password hazifanani")
            else:
                ok, msg = register(u2, p2)
                (st.success if ok else st.error)(msg)

    st.stop()

# ---------- Main app ----------
uid = st.session_state.user_id

st.title("MyDesk")
menu = st.sidebar.radio(
    "Menu", ["Home", "Expenses", "To-Do", "Wateja", "Invoice", "Risiti"]
)
st.sidebar.write(f"Umeingia kama: **{st.session_state.username}**")
if st.sidebar.button("Logout"):
    st.session_state.user_id = None
    st.session_state.username = None
    st.session_state.pop("last_receipt", None)
    st.rerun()


# ---------- HOME ----------
if menu == "Home":
    st.subheader("Home")
    st.write(f"Karibu {st.session_state.username}! Hii ni app yako ya kila siku.")

    df = load_expenses(uid)
    todos = load_todos(uid)
    customers = load_customers(uid)
    receipts = load_receipts(uid)
    income = df[df["Type"] == "Income"]["Amount"].sum()
    expense = df[df["Type"] == "Expense"]["Amount"].sum()
    pending = int((~todos["Done"]).sum()) if not todos.empty else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Balance", f"{income - expense:,.0f} TSh")
    c2.metric("Expenses", f"{expense:,.0f} TSh")
    c3.metric("Tasks zilizobaki", pending)
    c4, c5 = st.columns(2)
    c4.metric("Wateja", len(customers))
    c5.metric("Risiti zilizotolewa", len(receipts))

    st.info("Chagua zana kwenye menu upande wa kushoto.")


# ---------- EXPENSES ----------
elif menu == "Expenses":
    st.subheader("Expenses")

    with st.form("add_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        d = c1.date_input("Date", date.today())
        t = c2.selectbox("Type", ["Expense", "Income"])
        cat = c1.selectbox("Category", CATEGORIES)
        amount = c2.number_input("Amount (TSh)", min_value=0, step=500)
        desc = st.text_input("Description")
        submit = st.form_submit_button("Save")

    if submit:
        if amount > 0:
            run(
                "INSERT INTO expenses (user_id, date, type, category, description, amount) VALUES (?,?,?,?,?,?)",
                (uid, d.isoformat(), t, cat, desc, float(amount)),
            )
            st.success("Imehifadhiwa!")
        else:
            st.warning("Weka amount kubwa kuliko 0")

    df = load_expenses(uid)

    st.markdown("### Chuja")
    f1, f2 = st.columns(2)
    months = sorted(df["Date"].dt.strftime("%Y-%m").dropna().unique(), reverse=True)
    month = f1.selectbox("Mwezi", ["Zote"] + months)
    cats = f2.multiselect("Category", CATEGORIES)

    view = df.copy()
    if month != "Zote":
        view = view[view["Date"].dt.strftime("%Y-%m") == month]
    if cats:
        view = view[view["Category"].isin(cats)]

    income = view[view["Type"] == "Income"]["Amount"].sum()
    expense = view[view["Type"] == "Expense"]["Amount"].sum()
    m1, m2, m3 = st.columns(3)
    m1.metric("Income", f"{income:,.0f} TSh")
    m2.metric("Expenses", f"{expense:,.0f} TSh")
    m3.metric("Balance", f"{income - expense:,.0f} TSh")

    exp = view[view["Type"] == "Expense"]
    if not exp.empty:
        st.markdown("### Matumizi kwa Category")
        st.bar_chart(exp.groupby("Category")["Amount"].sum())

    st.markdown("### Hariri / Futa")
    if view.empty:
        st.write("Hakuna data.")
    else:
        st.caption("Bonyeza kisanduku kubadilisha. Tiki 'Delete' kufuta mstari.")
        edit_df = view.copy()
        edit_df["Delete"] = False
        edited = st.data_editor(
            edit_df,
            column_config={
                "id": None,
                "Date": st.column_config.DateColumn("Date"),
                "Type": st.column_config.SelectboxColumn("Type", options=["Expense", "Income"]),
                "Category": st.column_config.SelectboxColumn("Category", options=CATEGORIES),
                "Amount": st.column_config.NumberColumn("Amount", min_value=0, step=500),
            },
        )

        if st.button("Hifadhi mabadiliko"):
            conn = sqlite3.connect(DB)
            for _, r in edited.iterrows():
                rid = int(r["id"])
                if r["Delete"]:
                    conn.execute(
                        "DELETE FROM expenses WHERE id=? AND user_id=?", (rid, uid)
                    )
                else:
                    dt = pd.to_datetime(r["Date"], errors="coerce")
                    dt_str = dt.strftime("%Y-%m-%d") if pd.notna(dt) else None
                    dsc = "" if pd.isna(r["Description"]) else str(r["Description"])
                    conn.execute(
                        "UPDATE expenses SET date=?, type=?, category=?, description=?, amount=? WHERE id=? AND user_id=?",
                        (dt_str, r["Type"], r["Category"], dsc, float(r["Amount"]), rid, uid),
                    )
            conn.commit()
            conn.close()
            st.rerun()

        st.download_button(
            "Pakua Excel",
            to_excel(view),
            file_name="expenses.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


# ---------- TO-DO ----------
elif menu == "To-Do":
    st.subheader("To-Do")

    with st.form("todo_form", clear_on_submit=True):
        task = st.text_input("Task mpya")
        add = st.form_submit_button("Add")

    if add and task.strip():
        run(
            "INSERT INTO todos (user_id, task, done) VALUES (?, ?, 0)",
            (uid, task.strip()),
        )
        st.rerun()

    todos = load_todos(uid)

    if todos.empty:
        st.write("Hakuna task bado.")
    else:
        changed = False
        for _, row in todos.iterrows():
            tid = int(row["id"])
            done = st.checkbox(row["Task"], value=bool(row["Done"]), key=f"task_{tid}")
            if done != bool(row["Done"]):
                run(
                    "UPDATE todos SET done=? WHERE id=? AND user_id=?",
                    (int(done), tid, uid),
                )
                changed = True
        if changed:
            st.rerun()

        if st.button("Futa zilizokamilika"):
            run("DELETE FROM todos WHERE done=1 AND user_id=?", (uid,))
            st.rerun()


# ---------- WATEJA ----------
elif menu == "Wateja":
    st.subheader("Wateja")

    with st.form("cust_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        cname = c1.text_input("Jina la mteja")
        cphone = c2.text_input("Namba ya simu")
        add_c = st.form_submit_button("Hifadhi mteja")

    if add_c:
        if cname.strip():
            run(
                "INSERT INTO customers (user_id, name, phone) VALUES (?,?,?)",
                (uid, cname.strip(), cphone.strip()),
            )
            st.success("Mteja amehifadhiwa!")
            st.rerun()
        else:
            st.warning("Weka jina la mteja")

    customers = load_customers(uid)
    if customers.empty:
        st.write("Hakuna wateja bado.")
    else:
        st.caption("Bonyeza kisanduku kubadilisha. Tiki 'Delete' kufuta mteja.")
        cdf = customers.copy()
        cdf["Delete"] = False
        cedited = st.data_editor(cdf, column_config={"id": None})

        if st.button("Hifadhi mabadiliko ya wateja"):
            conn = sqlite3.connect(DB)
            for _, r in cedited.iterrows():
                cid = int(r["id"])
                if r["Delete"]:
                    conn.execute(
                        "DELETE FROM customers WHERE id=? AND user_id=?", (cid, uid)
                    )
                else:
                    nm = "" if pd.isna(r["Name"]) else str(r["Name"])
                    ph = "" if pd.isna(r["Phone"]) else str(r["Phone"])
                    conn.execute(
                        "UPDATE customers SET name=?, phone=? WHERE id=? AND user_id=?",
                        (nm, ph, cid, uid),
                    )
            conn.commit()
            conn.close()
            st.rerun()


# ---------- INVOICE ----------
elif menu == "Invoice":
    st.subheader("Toa Risiti")

    customers = load_customers(uid)
    business = st.text_input("Jina la biashara", get_business(uid))

    options = ["+ Mteja mpya"] + customers["Name"].tolist()
    choice = st.selectbox("Mteja", options)

    save_new = False
    if choice == "+ Mteja mpya":
        c1, c2 = st.columns(2)
        customer = c1.text_input("Jina la mteja")
        phone = c2.text_input("Namba ya simu")
        save_new = st.checkbox("Hifadhi mteja huyu kwenye orodha ya wateja")
    else:
        row = customers[customers["Name"] == choice].iloc[0]
        customer = row["Name"]
        phone = "" if pd.isna(row["Phone"]) else row["Phone"]
        st.caption(f"Simu: {phone if phone else '-'}")

    st.write("Ongeza bidhaa (bonyeza + chini ya table kuongeza mstari):")
    items = st.data_editor(
        pd.DataFrame([{"Item": "", "Qty": 1, "Price": 0}]),
        num_rows="dynamic",
        key="invoice_items",
    )

    items["Qty"] = pd.to_numeric(items["Qty"], errors="coerce").fillna(0)
    items["Price"] = pd.to_numeric(items["Price"], errors="coerce").fillna(0)
    items["Total"] = items["Qty"] * items["Price"]
    valid = items[items["Item"].fillna("").astype(str).str.strip() != ""]
    grand = valid["Total"].sum()

    st.metric("Jumla", f"{grand:,.0f} TSh")
    as_income = st.checkbox("Rekodi kama Income kwenye Expenses", value=True)

    if st.button("Tengeneza Risiti"):
        if valid.empty or grand <= 0:
            st.warning("Ongeza angalau bidhaa moja yenye bei")
        elif not customer.strip():
            st.warning("Weka jina la mteja")
        else:
            lines = [
                f"{r['Item']} x{int(r['Qty'])} @ {r['Price']:,.0f} = {r['Total']:,.0f}"
                for _, r in valid.iterrows()
            ]
            items_text = "\n".join(lines)
            today = date.today().isoformat()

            conn = sqlite3.connect(DB)
            n = conn.execute(
                "SELECT COUNT(*) FROM receipts WHERE user_id=?", (uid,)
            ).fetchone()[0]
            no = n + 1
            conn.execute(
                "INSERT INTO receipts (user_id, receipt_no, date, business, customer, phone, items, total) VALUES (?,?,?,?,?,?,?,?)",
                (uid, no, today, business, customer.strip(), phone, items_text, float(grand)),
            )
            conn.execute("UPDATE users SET business=? WHERE id=?", (business, uid))
            if save_new:
                conn.execute(
                    "INSERT INTO customers (user_id, name, phone) VALUES (?,?,?)",
                    (uid, customer.strip(), phone.strip()),
                )
            if as_income:
                conn.execute(
                    "INSERT INTO expenses (user_id, date, type, category, description, amount) VALUES (?,?,?,?,?,?)",
                    (uid, today, "Income", "Other", f"Risiti {no:04d} - {customer.strip()}", float(grand)),
                )
            conn.commit()
            conn.close()

            st.session_state.last_receipt = build_receipt(
                business, no, today, customer.strip(), phone, items_text, grand
            )
            st.session_state.last_receipt_no = no
            st.success(f"Risiti Na {no:04d} imehifadhiwa!")

    if st.session_state.get("last_receipt"):
        st.code(st.session_state.last_receipt)
        st.download_button(
            "Pakua Risiti (.txt)",
            st.session_state.last_receipt,
            file_name=f"risiti_{st.session_state.get('last_receipt_no', 0):04d}.txt",
        )


# ---------- RISITI (historia) ----------
elif menu == "Risiti":
    st.subheader("Historia ya Risiti")

    rec = load_receipts(uid)
    if rec.empty:
        st.write("Hakuna risiti bado.")
    else:
        search = st.text_input("Tafuta kwa jina la mteja")
        shown = rec
        if search.strip():
            shown = rec[rec["customer"].str.contains(search.strip(), case=False, na=False)]

        table = shown[["receipt_no", "date", "customer", "total"]].rename(
            columns={"receipt_no": "Na", "date": "Tarehe", "customer": "Mteja", "total": "Jumla (TSh)"}
        )
        st.dataframe(table, hide_index=True)
        st.metric("Jumla ya mauzo (yaliyoonyeshwa)", f"{shown['total'].sum():,.0f} TSh")

        if not shown.empty:
            labels = [
                f"{int(r.receipt_no):04d} - {r.customer} ({r.total:,.0f} TSh)"
                for r in shown.itertuples()
            ]
            pick = st.selectbox("Chagua risiti kuiona", labels)
            r = shown.iloc[labels.index(pick)]
            text = build_receipt(
                r["business"], int(r["receipt_no"]), r["date"],
                r["customer"], r["phone"], r["items"], r["total"],
            )
            st.code(text)
            st.download_button(
                "Pakua Risiti (.txt)",
                text,
                file_name=f"risiti_{int(r['receipt_no']):04d}.txt",
                key="dl_history",
            )