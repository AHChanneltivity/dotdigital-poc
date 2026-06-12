import requests
import os
from datetime import datetime

CT_BASE = "https://api.channeltivity.com/dotdigitalpoc/api/v1"
USERNAME = os.environ["CT_USERNAME"]
PASSWORD = os.environ["CT_PASSWORD"]

PARTNER_TYPE_MAP = {"2": "Gold", "3": "Silver", "4": "Platinum"}

TIER_THRESHOLDS = {
    "Silver": {"next": "Gold", "deals": 3, "acv": 100000},
    "Gold": {"next": "Platinum", "deals": 5, "acv": 300000},
    "Platinum": {"next": None, "deals": None, "acv": None}
}

def login():
    r = requests.post(f"{CT_BASE}/Login", json={"Username": USERNAME, "Password": PASSWORD},
                      headers={"Content-Type": "application/json; charset=UTF-8"})
    return r.text.strip().strip('"')

def query(session_id, q, locator=None):
    payload = {"QueryLocator": locator} if locator else {"Query": q}
    r = requests.post(f"{CT_BASE}/Query", json=payload,
                      headers={"Content-Type": "application/json; charset=UTF-8", "Ctvt-SessionId": session_id})
    return r.json()

def get_all(session_id, q):
    results = []
    data = query(session_id, q)
    results.extend(data.get("Entities", []))
    while not data.get("Done") and data.get("QueryLocator"):
        data = query(session_id, None, locator=data["QueryLocator"])
        results.extend(data.get("Entities", []))
    return results

def field_val(entity, name):
    for f in entity.get("Fields", []):
        if f["Name"] == name:
            return f["Value"]
    return None

def main():
    session_id = login()
    current_year = datetime.now().year

    deals = get_all(session_id, f"SELECT Key, Amount, CloseDate, OwnerOrgId, RegistrationStatus FROM DealRegistration WHERE RegistrationStatus = '3' AND CloseDate >= '{current_year}-01-01'")
    print(f"Total won deals: {len(deals)}")

    orgs = get_all(session_id, "SELECT Key, Name, PartnerType FROM Organization")
    org_map = {}
    for org in orgs:
        key = field_val(org, "Key")
        org_map[key] = {
            "name": field_val(org, "Name") or "Unknown",
            "partnerType": PARTNER_TYPE_MAP.get(field_val(org, "PartnerType") or "", "Unknown")
        }

    partners = {}
    for deal in deals:
        close_date = field_val(deal, "CloseDate") or ""
        if not close_date.startswith(str(current_year)):
            continue
        org_id = field_val(deal, "OwnerOrgId")
        amount = float(field_val(deal, "Amount") or 0)
        org_info = org_map.get(org_id, {"name": "Unknown", "partnerType": "Unknown"})
        if org_id not in partners:
            partners[org_id] = {
                "orgId": org_id,
                "orgName": org_info["name"],
                "dealCount": 0,
                "totalACV": 0,
                "partnerType": org_info["partnerType"]
            }
        partners[org_id]["dealCount"] += 1
        partners[org_id]["totalACV"] += amount

    partner_list = list(partners.values())

    snapshot = datetime.now().strftime("%B %Y")
    total = len(partner_list)
    silver = sum(1 for p in partner_list if p["partnerType"] == "Silver")
    gold = sum(1 for p in partner_list if p["partnerType"] == "Gold")
    platinum = sum(1 for p in partner_list if p["partnerType"] == "Platinum")

    tier_colors = {
        "Silver": "background:#D3D1C7;color:#444441",
        "Gold": "background:#FAC775;color:#633806",
        "Platinum": "background:#CECBF6;color:#3C3489"
    }

    rows = ""
    for p in sorted(partner_list, key=lambda x: x["orgName"]):
        t = p["partnerType"]
        threshold = TIER_THRESHOLDS.get(t, TIER_THRESHOLDS["Silver"])
        deal_pct = min(100, round(p["dealCount"] / threshold["deals"] * 100)) if threshold["deals"] else 100
        acv_pct = min(100, round(p["totalACV"] / threshold["acv"] * 100)) if threshold["acv"] else 100
        leading_pct = max(deal_pct, acv_pct)

        if threshold["next"]:
            deals_remaining = threshold["deals"] - p["dealCount"]
            acv_remaining = threshold["acv"] - p["totalACV"]
            if deals_remaining <= 0 or acv_remaining <= 0:
                to_go = "Threshold met — promoting next cycle"
                status = "met"
            elif deal_pct >= acv_pct:
                to_go = f"{deals_remaining} deals to go"
                status = "not-met"
            else:
                to_go = f"${round(acv_remaining / 1000)}k ACV to go"
                status = "not-met"
        else:
            to_go = "Top tier"
            status = "met"

        progress_color = "#1D9E75" if leading_pct >= 80 else "#EF9F27" if leading_pct >= 40 else "#E24B4A"
        badge_style = tier_colors.get(t, tier_colors["Silver"])

        rows += f"""
        <tr class="partner-row" data-status="{status}">
            <td style="padding:12px 16px;border-bottom:1px solid #eee;font-weight:500;font-size:14px;">{p['orgName']}</td>
            <td style="padding:12px 16px;border-bottom:1px solid #eee;">
                <span style="{badge_style};font-size:11px;font-weight:600;padding:3px 10px;border-radius:20px;">{t}</span>
            </td>
            <td style="padding:12px 16px;border-bottom:1px solid #eee;font-size:13px;color:#666;">{threshold['next'] or '—'}</td>
            <td style="padding:12px 16px;border-bottom:1px solid #eee;font-size:13px;">
                {p['dealCount']} / {threshold['deals'] or '—'}
                <div style="background:#eee;border-radius:4px;height:5px;width:100%;margin-top:5px;">
                    <div style="width:{deal_pct}%;background:#1D9E75;height:5px;border-radius:4px;"></div>
                </div>
            </td>
            <td style="padding:12px 16px;border-bottom:1px solid #eee;font-size:13px;">
                ${round(p['totalACV'] / 1000)}k / {('$' + str(threshold['acv'] // 1000) + 'k') if threshold['acv'] else '—'}
                <div style="background:#eee;border-radius:4px;height:5px;width:100%;margin-top:5px;">
                    <div style="width:{acv_pct}%;background:#378ADD;height:5px;border-radius:4px;"></div>
                </div>
            </td>
            <td style="padding:12px 16px;border-bottom:1px solid #eee;font-size:13px;color:{progress_color};font-weight:600;">
                {leading_pct}%<br>
                <span style="font-weight:400;color:#888;font-size:12px;">{to_go}</span>
            </td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dotdigital Partner Tier Dashboard</title>
</head>
<body style="margin:0;padding:2rem;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#fff;">
<div style="max-width:960px;margin:0 auto;">
    <h1 style="font-size:22px;font-weight:600;margin:0 0 4px;color:#222;">Partner Tier Progress</h1>
    <p style="font-size:13px;color:#999;margin:0 0 1.5rem;">Snapshot: {snapshot} &nbsp;·&nbsp; Calendar year {current_year}</p>
    <div style="display:flex;gap:12px;margin-bottom:2rem;flex-wrap:wrap;">
        <div style="background:#f7f7f7;border-radius:10px;padding:16px 20px;min-width:120px;">
            <div style="font-size:12px;color:#999;margin-bottom:4px;">Total Partners</div>
            <div style="font-size:26px;font-weight:600;color:#222;">{total}</div>
        </div>
        <div style="background:#f7f7f7;border-radius:10px;padding:16px 20px;min-width:120px;">
            <div style="font-size:12px;color:#999;margin-bottom:4px;">Silver</div>
            <div style="font-size:26px;font-weight:600;color:#222;">{silver}</div>
        </div>
        <div style="background:#f7f7f7;border-radius:10px;padding:16px 20px;min-width:120px;">
            <div style="font-size:12px;color:#999;margin-bottom:4px;">Gold</div>
            <div style="font-size:26px;font-weight:600;color:#222;">{gold}</div>
        </div>
        <div style="background:#f7f7f7;border-radius:10px;padding:16px 20px;min-width:120px;">
            <div style="font-size:12px;color:#999;margin-bottom:4px;">Platinum</div>
            <div style="font-size:26px;font-weight:600;color:#222;">{platinum}</div>
        </div>
    </div>
    <div style="display:flex;gap:8px;margin-bottom:1rem;">
        <button onclick="filterRows('all')" id="btn-all" style="padding:6px 16px;border-radius:20px;border:1px solid #ddd;background:#222;color:#fff;font-size:13px;cursor:pointer;">All</button>
        <button onclick="filterRows('met')" id="btn-met" style="padding:6px 16px;border-radius:20px;border:1px solid #ddd;background:#fff;color:#222;font-size:13px;cursor:pointer;">Threshold met</button>
        <button onclick="filterRows('not-met')" id="btn-not-met" style="padding:6px 16px;border-radius:20px;border:1px solid #ddd;background:#fff;color:#222;font-size:13px;cursor:pointer;">Not yet met</button>
    </div>
    <div style="border:1px solid #eee;border-radius:10px;overflow:hidden;">
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
            <thead>
                <tr style="background:#f7f7f7;">
                    <th style="padding:12px 16px;text-align:left;font-weight:500;font-size:12px;color:#888;text-transform:uppercase;letter-spacing:0.5px;">Partner</th>
                    <th style="padding:12px 16px;text-align:left;font-weight:500;font-size:12px;color:#888;text-transform:uppercase;letter-spacing:0.5px;">Tier</th>
                    <th style="padding:12px 16px;text-align:left;font-weight:500;font-size:12px;color:#888;text-transform:uppercase;letter-spacing:0.5px;">Next Tier</th>
                    <th style="padding:12px 16px;text-align:left;font-weight:500;font-size:12px;color:#888;text-transform:uppercase;letter-spacing:0.5px;">Won Deals</th>
                    <th style="padding:12px 16px;text-align:left;font-weight:500;font-size:12px;color:#888;text-transform:uppercase;letter-spacing:0.5px;">ACV</th>
                    <th style="padding:12px 16px;text-align:left;font-weight:500;font-size:12px;color:#888;text-transform:uppercase;letter-spacing:0.5px;">Progress</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
</div>
<script>
function filterRows(status) {{
    document.querySelectorAll('.partner-row').forEach(row => {{
        row.style.display = (status === 'all' || row.dataset.status === status) ? '' : 'none';
    }});
    document.querySelectorAll('button').forEach(btn => {{
        btn.style.background = '#fff';
        btn.style.color = '#222';
    }});
    document.getElementById('btn-' + status).style.background = '#222';
    document.getElementById('btn-' + status).style.color = '#fff';
}}
</script>
</body>
</html>"""

    with open("index.html", "w") as f:
        f.write(html)

    print(f"Dashboard generated with {total} partners")

if __name__ == "__main__":
    main()