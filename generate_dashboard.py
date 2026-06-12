import requests
import json
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

    # Get all approved closed deals
    deals = get_all(session_id, "SELECT Key, Amount, CloseDate, OwnerOrgId, OwnerOrgId_Name FROM DealRegistration WHERE RegistrationStatus = 'Approved (Closed)'")

    # Aggregate by partner
    partners = {}
    for deal in deals:
        close_date = field_val(deal, "CloseDate") or ""
        if not close_date.startswith(str(current_year)):
            continue
        org_id = field_val(deal, "OwnerOrgId")
        org_name = field_val(deal, "OwnerOrgId_Name") or "Unknown"
        amount = float(field_val(deal, "Amount") or 0)
        if org_id not in partners:
            partners[org_id] = {"orgId": org_id, "orgName": org_name, "dealCount": 0, "totalACV": 0, "partnerType": "Unknown"}
        partners[org_id]["dealCount"] += 1
        partners[org_id]["totalACV"] += amount

    partner_list = list(partners.values())

    # Get partner types
    if partner_list:
        org_ids = [p["orgId"] for p in partner_list]
        for partner in partner_list:
            data = get_all(session_id, f"SELECT Key, PartnerType FROM Organization WHERE Key = '{partner['orgId']}'")
            if data:
                pt = field_val(data[0], "PartnerType")
                partner["partnerType"] = PARTNER_TYPE_MAP.get(pt, "Unknown")

    # Build HTML
    snapshot = datetime.now().strftime("%B %Y")
    total = len(partner_list)
    silver = sum(1 for p in partner_list if p["partnerType"] == "Silver")
    gold = sum(1 for p in partner_list if p["partnerType"] == "Gold")
    platinum = sum(1 for p in partner_list if p["partnerType"] == "Platinum")

    tier_colors = {
        "Silver": ("background:#D3D1C7;color:#444441", ),
        "Gold": ("background:#FAC775;color:#633806", ),
        "Platinum": ("background:#CECBF6;color:#3C3489", )
    }

    rows = ""
    for p in sorted(partner_list, key=lambda x: x["orgName"]):
        t = p["partnerType"]
        threshold = TIER_THRESHOLDS.get(t, TIER_THRESHOLDS["Silver"])
        deal_pct = min(100, round(p["dealCount"] / threshold["deals"] * 100)) if threshold["deals"] else 100
        acv_pct = min(100, round(p["totalACV"] / threshold["acv"] * 100)) if threshold["acv"] else 100
        leading_pct = max(deal_pct, acv_pct)
        if threshold["next"]:
            to_go = f"{threshold['deals'] - p['dealCount']} deals to go" if deal_pct >= acv_pct else f"${round((threshold['acv'] - p['totalACV']) / 1000)}k ACV to go"
        else:
            to_go = "Top tier"
        progress_color = "#1D9E75" if leading_pct >= 80 else "#EF9F27" if leading_pct >= 40 else "#E24B4A"
        badge_style = tier_colors.get(t, tier_colors["Silver"])[0]

        rows += f"""
        <tr>
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
</body>
</html>"""

    with open("index.html", "w") as f:
        f.write(html)

    print(f"Dashboard generated with {total} partners")

if __name__ == "__main__":
    main()
