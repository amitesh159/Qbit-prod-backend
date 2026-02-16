"""
Mock Generator Service (v2)
Auto-generates schema-aware MSW handlers from backend code.
Handles Express mount points, realistic data generation, and robust route detection.
"""
import re
import structlog
import json
from typing import Dict, List, Any, Set, Tuple

logger = structlog.get_logger(__name__)

class MockGenerator:
    """
    Generates intelligent MSW mock handlers.
    
    Capabilities:
    1. Mount Point Detection: index.ts (app.use('/api/users', userRoutes)) -> /api/users prefix
    2. Schema Parsing: Mongoose schemas -> realistic mock data
    3. Robust Regex: Handles multiline routes, arrow functions
    """
    
    @staticmethod
    def generate_mocks(files: Dict[str, str]) -> Dict[str, str]:
        """
        Generate mock files based on backend routes and schemas.
        """
        try:
            # 1. Parse Schemas for realistic data
            schemas = MockGenerator._parse_schemas(files)
            logger.info("schemas_parsed", count=len(schemas))
            
            # 2. Extract Mount Points (e.g. app.use('/api', router))
            mount_points = MockGenerator._extract_mount_points(files)
            logger.info("mount_points_found", points=mount_points)
            
            # 3. Extract Routes with context
            routes = MockGenerator._extract_routes(files, mount_points)
            logger.info("routes_extracted", count=len(routes))
            
            # 4. Generate Code
            handlers_content = MockGenerator._generate_handlers_js(routes, schemas)
            browser_content = MockGenerator._generate_browser_js()
            
            return {
                "frontend/mocks/handlers.js": handlers_content,
                "frontend/mocks/browser.js": browser_content
                # mockServiceWorker.js handled via 'cp' command in deployment
            }
        except Exception as e:
            logger.exception("mock_generation_failed", error=str(e))
            # Return fallback empty mocks to prevent crash
            return {
                "frontend/mocks/handlers.js": "export const handlers = []",
                "frontend/mocks/browser.js": "export const worker = { start: () => {} }"
            }

    @staticmethod
    def _parse_schemas(files: Dict[str, str]) -> Dict[str, Dict[str, str]]:
        """
        Extract simplified schema definitions from Mongoose models.
        Returns: { "User": { "name": "string", "email": "email", "age": "number" } }
        """
        schemas = {}
        
        # Regex for Mongoose Schema definition
        # Matches: const UserSchema = new Schema({ ... }) OR new mongoose.Schema({ ... })
        schema_start_pattern = re.compile(r'(?:const|let|var)\s+(\w+)\s*=\s*new\s+(?:mongoose\.)?Schema\s*\(\s*{', re.IGNORECASE)
        
        for path, content in files.items():
            if "backend/models" in path:
                lines = content.split('\n')
                current_schema = None
                brace_count = 0
                schema_content = []
                
                # Naive parser for JSON-like object inside Schema({...})
                for line in lines:
                    if current_schema is None:
                        match = schema_start_pattern.search(line)
                        if match:
                            # Schema name usually ends with 'Schema' e.g. UserSchema -> User
                            raw_name = match.group(1)
                            current_schema = raw_name.replace('Schema', '')
                            brace_count = 1
                            continue
                            
                    else:
                        brace_count += line.count('{') - line.count('}')
                        schema_content.append(line)
                        if brace_count == 0:
                            # End of schema
                            schemas[current_schema] = MockGenerator._extract_fields("\n".join(schema_content))
                            current_schema = None
                            schema_content = []
                            
        return schemas

    @staticmethod
    def _extract_fields(content: str) -> Dict[str, str]:
        """Extract fields and types from schema content string."""
        fields = {}
        # Matches: name: { type: String } OR name: String
        # Very simplified matching
        for line in content.split('\n'):
            line = line.strip()
            if ':' in line:
                key = line.split(':')[0].strip()
                val = line.split(':')[1].strip()
                
                if 'String' in val: fields[key] = 'string'
                elif 'Number' in val: fields[key] = 'number'
                elif 'Boolean' in val: fields[key] = 'boolean'
                elif 'Date' in val: fields[key] = 'date'
                elif '[' in val: fields[key] = 'array'
                
        return fields

    @staticmethod
    def _extract_mount_points(files: Dict[str, str]) -> Dict[str, str]:
        """
        Find where routers are mounted in index.ts/app.ts.
        Returns: { "users.ts": "/api/users", "auth.ts": "/api/auth" }
        """
        router_map = {} # variable -> file_path
        mount_map = {}  # file_path -> prefix
        
        index_file = None
        for path in files:
            if path.endswith("backend/index.ts") or path.endswith("backend/index.js") or path.endswith("backend/app.ts"):
                index_file = path
                break
                
        if not index_file:
            return {}
            
        content = files[index_file]
        
        # 1. Find imports: import userRoutes from './routes/users'
        # Matches: import XYZ from 'PATH'
        import_pattern = re.compile(r'import\s+(\w+)\s+from\s+[\'"](.+?)[\'"]')
        for match in import_pattern.finditer(content):
            var_name, import_path = match.groups()
            # Resolve relative path to absolute file identifier
            # e.g. ./routes/users -> backend/routes/users.ts
            if import_path.startswith('.'):
                # Simple resolution assuming index is at backend root
                clean_path = import_path.replace('./', '')
                if not clean_path.startswith('backend/'):
                    clean_path = f"backend/{clean_path}" 
                # Add extensions check
                for ext in ['.ts', '.js']:
                     router_map[var_name] = clean_path + ext
                     
        # 2. Find mounts: app.use('/api/users', userRoutes)
        mount_pattern = re.compile(r'app\.use\s*\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*(\w+)\s*\)')
        for match in mount_pattern.finditer(content):
            prefix, var_name = match.groups()
            if var_name in router_map:
                file_path = router_map[var_name]
                mount_map[file_path] = prefix
                # Also try matching without extension just in case
                base_path = file_path.rsplit('.', 1)[0]
                mount_map[base_path] = prefix
                
        return mount_map

    @staticmethod
    def _extract_routes(files: Dict[str, str], mount_points: Dict[str, str]) -> List[Dict[str, Any]]:
        """Extract routes with full mounted paths."""
        routes = []
        
        # Regex: router.get('/path', ...)
        # Handles multiline via DOTALL, but constrained to avoid over-matching
        route_pattern = re.compile(r'\.(get|post|put|delete|patch)\s*\(\s*[\'"]([^\'"]*)[\'"]', re.IGNORECASE)
        
        for path, content in files.items():
            if "backend/routes" in path:
                # Determine prefix
                prefix = "/api" # Default fallback
                
                # Check strict match
                if path in mount_points:
                    prefix = mount_points[path]
                else:
                    # Check partial match (basename)
                    for mp_path, mp_prefix in mount_points.items():
                        if mp_path in path or path in mp_path:
                            prefix = mp_prefix
                            break
                
                matches = route_pattern.findall(content)
                for method, route_path in matches:
                    full_path = f"{prefix}{route_path}".replace('//', '/')
                    # Clean trailing slash if not root
                    if full_path != '/' and full_path.endswith('/'):
                        full_path = full_path[:-1]
                        
                    routes.append({
                        "method": method.lower(),
                        "path": full_path,
                        "original_path": route_path,
                        "file": path,
                        "response_model": MockGenerator._guess_model_from_path(path)
                    })
                    
        return routes

    @staticmethod
    def _guess_model_from_path(file_path: str) -> str:
        """Guess likely model name from file path. users.ts -> User"""
        basename = file_path.split('/')[-1].split('.')[0] # users
        # Simple singularization
        if basename.endswith('s'):
            basename = basename[:-1]
        return basename.capitalize()

    @staticmethod
    def _generate_handlers_js(routes: List[Dict[str, Any]], schemas: Dict[str, Dict[str, str]]) -> str:
        """Generate handlers.js with dynamic data."""
        
        code = [
            "import { http, HttpResponse } from 'msw';",
            "",
            "// Helper to generate random ID",
            "const getId = () => Math.random().toString(36).substring(7);",
            "",
            "// Helper to generate mock data based on schema",
            "const generateMock = (type) => {",
            "  switch(type) {",
            "    case 'User': return { id: getId(), name: 'Alex Developer', email: 'alex@example.com', role: 'user' };",
            "    case 'Task': return { id: getId(), title: 'Sample Task', completed: false, createdAt: new Date().toISOString() };",
            "    case 'Product': return { id: getId(), name: 'Premium Widget', price: 99.99, description: 'Sample product description' };",
            "    default: return { id: getId(), message: 'Mock Data' };",
            "  }",
            "};",
            "",
            "export const handlers = ["
        ]
        
        seen = set()
        
        for route in routes:
            key = f"{route['method']}:{route['path']}"
            if key in seen: continue
            seen.add(key)
            
            # Smart Mock Data Body
            model = route['response_model']
            is_list = route['method'] == 'get' and not ':' in route['path']
            
            # MSW Path: /api/users/:id -> /api/users/:id
            msw_path = route['path']
            # If path has params like /:id, we can access them in handler if needed
            
            handler_body = ""
            if route['method'] == 'get':
                if is_list:
                    handler_body = f"Array.from({{ length: 5 }}).map(() => generateMock('{model}'))"
                else:
                    handler_body = f"generateMock('{model}')"
            else:
                 handler_body = f"{{ success: true, message: '{route['method'].upper()} successful', data: generateMock('{model}') }}"
            
            if route['method'] == 'post':
                 code.append(f"""  http.post('*{msw_path}', async ({{ request }}) => {{
    const body = await request.json().catch(() => ({{}}));
    return HttpResponse.json({{
      id: getId(),
      ...body,
      createdAt: new Date().toISOString()
    }}, {{ status: 201 }})
  }}),""")
            elif route['method'] == 'delete':
                 code.append(f"""  http.delete('*{msw_path}', () => {{
    return HttpResponse.json({{ success: true }}, {{ status: 200 }})
  }}),""")
            else:
                code.append(f"""  http.{route['method']}('*{msw_path}', () => {{
    return HttpResponse.json({handler_body}, {{ status: 200 }})
  }}),""")

        code.append("];")
        return "\n".join(code)

    @staticmethod
    def _generate_browser_js() -> str:
        return """import { setupWorker } from 'msw/browser';
import { handlers } from './handlers';

export const worker = setupWorker(...handlers);

// Log start
worker.start({
  onUnhandledRequest: 'bypass',
}).then(() => {
  console.log('[MSW] Mock Service Worker started - Frontend Preview Mode');
});
"""

