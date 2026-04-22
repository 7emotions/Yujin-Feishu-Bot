# Feishu Approval Definition Setup Guide

This document explains how to **manually create** the reimbursement approval definition in the Feishu admin console.

> ⚠️ This setup is REQUIRED before the bot can create approval instances. Do NOT skip this step.

---

## Step 1: Open Feishu Approval Admin Console

Navigate to:
```
https://www.feishu.cn/approval/admin/approvalList?devMode=on
```

> The `?devMode=on` query parameter is **critical** — it exposes the `definitionCode` in the URL.

## Step 2: Create New Approval

Click **新建审批** (New Approval).

## Step 3: Set Approval Name

Set the approval name to: **报销申请** (Expense Reimbursement)

## Step 4: Add Form Controls

Add the following form controls **in this exact order** with these exact settings:

| # | Control Label | Control Type | Required | Notes |
|---|---|---|---|---|
| 1 | 发票号码 | 单行文本 (input) | ✅ Yes | Invoice number |
| 2 | 报销金额 | 数字 (number) | ✅ Yes | Amount (numeric only) |
| 3 | 货币 | 单选 (radioV2) | ✅ Yes | Options: CNY, USD, EUR |
| 4 | 发票日期 | 日期 (date) | ✅ Yes | Format: YYYY-MM-DD |
| 5 | 供应商 | 单行文本 (input) | ✅ Yes | Vendor name |
| 6 | 费用类别 | 单选 (radioV2) | ✅ Yes | Options: 餐饮, 交通, 住宿, 办公, 其他 |
| 7 | 报销说明 | 多行文本 (textarea) | ❌ No | Optional description |
| 8 | 发票附件 | 附件 (attachmentV2) | ✅ Yes | Invoice file upload |

## Step 5: Set Approver

Set the approval flow to use a **fixed approver**:
- Use the `APPROVER_OPEN_ID` value from your `.env` file: `ou_f906e54608aa7d299378f699beae2aaa`
- Or search for the approver by name in the Feishu user search

## Step 6: Publish the Definition

Click **发布** (Publish) to activate the approval definition.

## Step 7: Get the `definitionCode` (APPROVAL_CODE)

After publishing, click **编辑** (Edit) on the approval definition.

Look at the browser URL — it will contain the approval definition code in this format:
```
https://www.feishu.cn/approval/admin/approvalDetail?approvalCode=XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX
```

Copy the `XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX` part — this is your `APPROVAL_CODE`.

Add it to `.env`:
```
APPROVAL_CODE=XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX
```

> ℹ️ The `devMode=on` parameter on the approvalList page also shows the `definitionCode` column directly in the list.

## Step 8: Get Widget IDs (FORM_FIELD_IDS)

The bot needs the widget ID of each form control to build the approval request payload.

### Method: Browser DevTools

1. Navigate to the approval definition preview page
2. Open **Browser DevTools** (F12) → **Network** tab
3. Refresh the page and look for an API call returning the form definition JSON
4. In the response, find the `widget_id` or `id` field for each control

Alternatively:
1. Open the approval definition in edit mode
2. Click each form control → the property panel on the right shows the control's `ID`

### Add to `.env`

Once you have the widget IDs, add them to `.env` as a JSON object:

```env
FORM_FIELD_IDS={"invoice_no": "widget1", "amount": "widget2", "currency": "widget3", "date": "widget4", "vendor": "widget5", "category": "widget6", "description": "widget7", "attachment": "widget8"}
```

---

## Summary of `.env` keys set in this guide

After completing all steps, these `.env` entries should be filled in:

```env
APPROVAL_CODE=XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX
FORM_FIELD_IDS={"invoice_no": "...", "amount": "...", "currency": "...", "date": "...", "vendor": "...", "category": "...", "description": "...", "attachment": "..."}
```

---

## Approval Instance API Reference

The bot creates instances by calling:

```
POST https://open.feishu.cn/open-apis/approval/v4/instances
Authorization: Bearer {tenant_access_token}

{
  "approval_code": "APPROVAL_CODE_FROM_ENV",
  "open_id": "user_open_id",
  "form": "[{\"id\": \"widget1\", \"type\": \"input\", \"value\": \"INV-001\"}, ...]",
  "node_approver_open_id_list": [{"key": "APPROVER_NODE_KEY", "value": ["APPROVER_OPEN_ID"]}],
  "uuid": "UUID-v4-UPPERCASE"
}
```

Note: `form` is a **JSON string** (double-encoded), not an object. The `attachmentV2` field value is `[file_code]` (an array of file code strings returned by the attachment upload API).
