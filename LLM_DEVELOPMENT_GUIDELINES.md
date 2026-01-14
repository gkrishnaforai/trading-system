# 🤖 LLM Development Guidelines

## 🎯 **CRITICAL: Read This Before Any Code Changes**

### 📋 **Mandatory Pre-Change Checklist**

Before making ANY changes to the codebase, you MUST:

1. **📖 Read Documentation First**
   - Read `python-worker/ROUTER_GUIDELINES.md` for any router changes
   - Read relevant README files in the directory you're modifying
   - Check for existing patterns in similar files

2. **🔍 Understand the Context**
   - What is the current issue/error?
   - What has been tried before?
   - What are the existing patterns?

3. **📝 Document Your Changes**
   - Why are you making this change?
   - What problem does it solve?
   - How did you test it?

## 🚨 **Router Development - READ THIS FIRST**

### **The #1 Rule: NO PREFIXES IN ROUTER FILES**

```python
# ❌ NEVER DO THIS - THIS IS WRONG
router = APIRouter(prefix="/api/v1/feature", tags=["feature"])

# ✅ ALWAYS DO THIS - THIS IS CORRECT
router = APIRouter(tags=["feature"])
```

### **The #2 Rule: PREFIXES ONLY IN api_server.py**

```python
# ✅ ONLY ADD PREFIXES HERE
app.include_router(feature_router, prefix="/api/v1/feature")
```

### **The #3 Rule: Test After Changes**

```bash
# Always test endpoints after router changes
curl http://localhost:8001/docs
curl http://localhost:8001/api/v1/feature/endpoint
```

## 🧠 **LLM Memory Management**

### **Problem**: LLM forgets previous fixes
### **Solution**: Create persistent documentation

#### **Before Any Router Change:**
1. Read `ROUTER_GUIDELINES.md`
2. Run `python validate_routers.py`
3. Check existing router patterns

#### **After Any Router Change:**
1. Run `python validate_routers.py`
2. Test key endpoints
3. Update documentation if needed

## 🔄 **Common Error Patterns**

### **404 Errors? Check This:**
1. Router has prefix in individual file → Remove it
2. Router missing prefix in api_server.py → Add it
3. Double prefix → Remove from individual file

### **Import Errors? Check This:**
1. Router file name matches import
2. Router variable exists
3. No syntax errors

### **Duplicate Element Errors? Check This:**
1. Add unique keys to Streamlit elements
2. Use session state or timestamps
3. Check for duplicate component IDs

## 📚 **Documentation Strategy**

### **For Each Major Component:**
1. **README.md** - Overview and usage
2. **GUIDELINES.md** - Rules and patterns
3. **validate_*.py** - Automated validation
4. **Examples** - Working code samples

### **For Router Development:**
1. `ROUTER_GUIDELINES.md` - Authoritative rules
2. `validate_routers.py` - Automated checking
3. Comments in each router file
4. Comments in api_server.py

## 🎯 **Decision Tree for Common Issues**

```
404 Error on Endpoint?
├── Is it a router endpoint?
│   ├── Yes → Check router prefix rules
│   │   ├── Router has prefix in file? → Remove it
│   │   ├── Router missing prefix in api_server.py? → Add it
│   │   └── Double prefix? → Remove from file
│   └── No → Check other issues
└── Not a router → Check other causes

Duplicate Element Error?
├── Streamlit component?
│   ├── Yes → Add unique key
│   └── No → Check other causes
└── Not Streamlit → Check other issues
```

## 🛠️ **Development Workflow**

### **For Router Changes:**
1. Read `ROUTER_GUIDELINES.md`
2. Make changes following guidelines
3. Run `python validate_routers.py`
4. Test endpoints manually
5. Commit changes

### **For Other Changes:**
1. Read relevant documentation
2. Follow existing patterns
3. Test changes
4. Update documentation
5. Commit changes

## 📝 **Template for Responses**

When fixing issues, always include:

### **Problem Analysis:**
- What was the error?
- What was the root cause?
- What patterns were violated?

### **Solution:**
- What was changed?
- Why does this fix it?
- How was it tested?

### **Prevention:**
- What documentation was updated?
- What validation was added?
- How to prevent this in the future?

## 🚀 **Emergency Procedures**

### **If You See Router 404s:**
1. Stop and read `ROUTER_GUIDELINES.md`
2. Run `python validate_routers.py`
3. Fix prefix issues
4. Test endpoints
5. Document the fix

### **If You See Duplicate Element Errors:**
1. Find all elements with same key
2. Add unique identifiers
3. Test the UI
4. Document the pattern

## 📖 **Key Files to Always Check**

### **For Router Issues:**
- `python-worker/ROUTER_GUIDELINES.md`
- `python-worker/app/api_server.py`
- `python-worker/validate_routers.py`
- Individual router files

### **For General Issues:**
- Relevant README files
- Existing similar implementations
- Test files
- Documentation

---

**⚠️ CRITICAL: This documentation is authoritative. Always read it before making changes!**
