import streamlit as st
import pandas as pd
from icalendar import Calendar
from datetime import datetime, timedelta, date
import requests
import re
from streamlit_calendar import calendar

st.set_page_config(page_title="Lodge Cleaning Schedule", layout="wide")
st.markdown("""
<style>
@keyframes blink {
  50% { opacity: 0; }
}
.blink {
  animation: blink 1s infinite;
  color: red;
  font-weight: bold;
  font-size: 1.2em;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div style='text-align:center;'>
    <h1 style='margin-bottom:0;'>🧽 Lodge Cleaning Dashboard</h1>
    <p style='margin-top:4px; font-size:1.2em;'>Optimised for iPad & Mobile Use</p>
</div>
""", unsafe_allow_html=True)

ical_urls = {
    "Hart Lodge": "https://www.airbnb.com/calendar/ical/684551794093413533.ics?s=e7dffe9e5582072cb8369f36ba013033&locale=en-GB",
    "Hare Lodge": "https://www.airbnb.com/calendar/ical/647083178501004223.ics?s=b855121c71bc4d263f21d5730d4c6187&locale=en-GB"
}

notes_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQsWb1eswUEYV57gvhkXJSdctNkcw7R8_MzrAavM-GjaZ87Mc2ICOky8gN-FU13ykrn6XestQrh2kfl/pub?output=csv"

@st.cache_data
def parse_ical(url, lodge_name):
    response = requests.get(url)
    if response.status_code != 200:
        st.error(f"Failed to fetch calendar for {lodge_name}")
        return pd.DataFrame()

    cal = Calendar.from_ical(response.content)
    bookings = []

    for component in cal.walk():
        if component.name == "VEVENT":
            start = component.get("DTSTART").dt
            end = component.get("DTEND").dt
            summary = str(component.get("SUMMARY"))
            description = str(component.get("DESCRIPTION"))
            start_date = start if isinstance(start, date) else start.date()
            end_date = end if isinstance(end, date) else end.date()
            bookings.append({
                "Lodge": lodge_name,
                "Start Date": pd.to_datetime(start_date),
                "End Date": pd.to_datetime(end_date),
                "Guest Name": summary,
                "Description": description,
                "IsBlocked": any(x in summary.lower() for x in ["blocked", "not available"])
            })

    return pd.DataFrame(bookings)

# Load iCal + manual bookings
dataframes = [parse_ical(url, name) for name, url in ical_urls.items()]
df = pd.concat(dataframes, ignore_index=True)

manual_sheet_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT3jByOC7ViBPMIbmds6PMdZu56KiDh7a2vNKRfi8K1nrf6ftabKTnOSqY_8tHK7-1LTZ1MOzyScayv/pub?output=csv"
try:
    manual_df = pd.read_csv(manual_sheet_url, parse_dates=["Start Date", "End Date"])
    manual_df = manual_df.dropna(subset=["Lodge", "Start Date", "End Date"])
    manual_df["IsBlocked"] = False
    df = pd.concat([df, manual_df], ignore_index=True)
except Exception as e:
    st.warning(f"Manual bookings could not be loaded: {e}")

# Load notes/tasks
notes_df = pd.DataFrame()
try:
    notes_df = pd.read_csv(notes_url)
    notes_df["Date"] = pd.to_datetime(notes_df["Date"])
except Exception as e:
    st.warning(f"Notes/tasks could not be loaded: {e}")

# Clean and sort
today = pd.to_datetime(datetime.today().date())
df = df.sort_values(by=["Start Date", "Lodge"]).reset_index(drop=True)
df['Start Date'] = pd.to_datetime(df['Start Date']).dt.normalize()
df['End Date'] = pd.to_datetime(df['End Date']).dt.normalize()

# Generate 60-day activity table
next_60_days = pd.date_range(start=today, periods=60)
activity = []
for date_ in next_60_days:
    co_list = []
    ci_list = []
    changeovers = []
    for lodge in ["Hart Lodge", "Hare Lodge"]:
        co = df[(df['Lodge'] == lodge) & (df['End Date'] == date_) & (~df['IsBlocked'])]
        ci = df[(df['Lodge'] == lodge) & (df['Start Date'] == date_) & (~df['IsBlocked'])]
        co_list.append(not co.empty)
        ci_list.append(not ci.empty)
        if not co.empty or not ci.empty:
            changeovers.append(f"{lodge}: {' & '.join(filter(None, ['Out' if not co.empty else '', 'In' if not ci.empty else '']))}")

    if co_list == [True, True] and ci_list == [True, True]:
        rag = "🔴 Turnaround in BOTH lodges!"
    elif co_list == [True, True] and ci_list == [False, False]:
        rag = "🔶 Double Checkout Only"
    elif co_list.count(True) == 1 and ci_list.count(True) == 1:
        rag = "🟡 Single Changeover"
    elif co_list.count(True) == 1 and ci_list.count(True) == 0:
        rag = "🟡 Single Changeover"
    elif ci_list.count(True) > 0:
        rag = "🟢 Check-in Only"
    else:
        rag = "🔷 Free"

    note_text = ""
    if not notes_df.empty:
        notes_for_day = notes_df[notes_df['Date'].dt.normalize() == date_]
        if not notes_for_day.empty:
            notes_joined = "; ".join(notes_for_day['Note'].astype(str).tolist())
            note_text = f" | 📝 Notes: {notes_joined}"

    activity.append({
        "title": f"{rag} {', '.join(changeovers)}{note_text}",
        "start": date_.strftime('%Y-%m-%d'),
        "end": date_.strftime('%Y-%m-%d'),
        "color": {
            "🔴 Turnaround in BOTH lodges!": "#b30000",
            "🔶 Double Checkout Only": "#e65100",
            "🟡 Single Changeover": "#f1c232",
            "🟢 Check-in Only": "#4caf50",
            "🔷 Free": "#a1d99b"
        }[rag]
    })

# Show today summary block
today_row = next((a for a in activity if a['start'] == today.strftime('%Y-%m-%d')), None)
if today_row:
    st.markdown(f"""
    <div style='text-align:center; margin: 20px 0;'>
        <h3 style='margin-bottom:0;'>📅 Today: {today.strftime('%A, %d %B %Y')}</h3>
        <div style='display:inline-block; background-color:{today_row['color']}; color:black; font-size:1.2em; padding:10px 20px; border-radius:12px; margin-top:8px; min-width: 260px;'>
            {today_row['title']}
        </div>
    </div>
    """, unsafe_allow_html=True)

# Double Turnaround Warning
upcoming_double_days = [a for a in activity if '🔴' in a['title'] and a['start'] > today.strftime('%Y-%m-%d')]
if upcoming_double_days:
    upcoming_str = ', '.join(pd.to_datetime([d['start'] for d in upcoming_double_days]).strftime('%A, %d %B %Y'))
    st.markdown(f"""
    <div class='blink' style='text-align:center; margin-top:10px;'>
   ⚠️ ALERT: Double Turnaround Days Coming!<br>
    <span style='font-size:0.9em;'>Upcoming: {upcoming_str}</span></div>
    """, unsafe_allow_html=True)

# Calendar View
calendar_options = {
    "initialView": 'listWeek',
    "height": 650,
    "headerToolbar": {
        "left": 'prev,today,next',
        "center": 'title',
        "right": 'dayGridMonth,timeGridWeek,listWeek'
    }
}
calendar(events=activity, options=calendar_options, key="cleaning-calendar")