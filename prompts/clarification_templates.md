# Case Lookup Clarification Templates

## Multiple Similar Names Template

```
I found {count} clients with similar names to "{search_name}". To ensure I contact the correct person, could you provide:

**Option 1:** Full name (first and last name)
**Option 2:** Email address  
**Option 3:** Phone number

**Matching clients found:**
{client_list}
```

## Multiple Different Names Template

```
I found {count} clients that could match "{search_name}". Please help me identify the correct case:

**Available clients:**
{client_list}

Could you provide:
- Full name, OR
- Email address, OR  
- Phone number, OR
- Tell me "#{number}" from the list above
```

## No Open Cases Found Template

```
I couldn't find any open cases for "{search_name}". 

**Options:**
1. The client name might be spelled differently - could you provide the full name?
2. This might be a closed case - should I search closed cases?
3. This might be a new client - should I create a new case?

Please let me know how you'd like me to proceed.
```

## Verification Confirmation Template

```
✅ **Case Verification**

I found this case for "{client_name}":
- **Email:** {email}
- **Phone:** {phone}  
- **Case Status:** {status}
- **Pending Documents:** {pending_count}

Is this the correct client? (Yes/No)
```

## High Confidence Match Template

```
✅ **Case Found**

Found case for **{client_name}** ({email})
- Case Status: {status}
- Pending Documents: {pending_count}
- Last Communication: {last_comm}

Proceeding with communication...
```

## Closed Case Found Template

```
⚠️ **Found Closed Case**

I found {count} closed case(s) for "{search_name}" but no open cases.

**Closed cases:**
{client_list}

**Options:**
1. Did you mean one of these closed cases?
2. Should I create a new case for this client?
3. Could you double-check the client name?
```

## Fuzzy Match Confirmation Template

```
🔍 **Similar Name Found**

I found a case for "{found_name}" which is similar to "{search_name}".

**Case Details:**
- **Client:** {found_name}
- **Email:** {email}
- **Status:** {status}

Is this the client you meant? (Yes/No)
```