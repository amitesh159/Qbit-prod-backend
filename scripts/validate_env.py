#!/usr/bin/env python3
"""
Qbit Environment Variables Validator
Validates all required environment variables before deployment to Render
"""

import os
import sys
from typing import Dict, List, Tuple
from urllib.parse import urlparse
import re


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header(text: str):
    """Print formatted header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text.center(70)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}\n")


def print_success(text: str):
    """Print success message"""
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")


def print_error(text: str):
    """Print error message"""
    print(f"{Colors.RED}✗ {text}{Colors.END}")


def print_warning(text: str):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")


def print_info(text: str):
    """Print info message"""
    print(f"{Colors.BLUE}ℹ {text}{Colors.END}")


def validate_mongodb_uri(uri: str) -> Tuple[bool, str]:
    """Validate MongoDB connection string"""
    if not uri:
        return False, "MongoDB URI is empty"
    
    if not uri.startswith(('mongodb://', 'mongodb+srv://')):
        return False, "MongoDB URI must start with 'mongodb://' or 'mongodb+srv://'"
    
    if '<password>' in uri or '<username>' in uri:
        return False, "MongoDB URI contains placeholder values"
    
    try:
        parsed = urlparse(uri)
        if not parsed.hostname:
            return False, "MongoDB URI is missing hostname"
        return True, "Valid MongoDB URI"
    except Exception as e:
        return False, f"Invalid MongoDB URI: {str(e)}"


def validate_redis_url(url: str) -> Tuple[bool, str]:
    """Validate Redis connection string"""
    if not url:
        return False, "Redis URL is empty"
    
    if not url.startswith('redis://'):
        return False, "Redis URL must start with 'redis://'"
    
    if '<password>' in url or '<host>' in url:
        return False, "Redis URL contains placeholder values"
    
    try:
        parsed = urlparse(url)
        if not parsed.hostname:
            return False, "Redis URL is missing hostname"
        if not parsed.port:
            return False, "Redis URL is missing port"
        return True, "Valid Redis URL"
    except Exception as e:
        return False, f"Invalid Redis URL: {str(e)}"


def validate_api_keys(keys: str, provider: str, expected_prefix: str) -> Tuple[bool, str]:
    """Validate API keys format"""
    if not keys:
        return False, f"{provider} API keys are empty"
    
    key_list = [k.strip() for k in keys.split(',')]
    
    if len(key_list) < 1:
        return False, f"{provider} requires at least 1 API key"
    
    for key in key_list:
        if not key.startswith(expected_prefix):
            return False, f"{provider} key must start with '{expected_prefix}'"
        if len(key) < 20:
            return False, f"{provider} key seems too short"
    
    return True, f"Valid {provider} API keys ({len(key_list)} keys)"


def validate_jwt_secret(secret: str) -> Tuple[bool, str]:
    """Validate JWT secret key"""
    if not secret:
        return False, "JWT secret is empty"
    
    if len(secret) < 32:
        return False, "JWT secret should be at least 32 characters"
    
    if secret == "your_secret_key_here" or secret == "change_me":
        return False, "JWT secret contains placeholder value"
    
    return True, f"Valid JWT secret ({len(secret)} characters)"


def validate_e2b_key(key: str) -> Tuple[bool, str]:
    """Validate E2B API key"""
    if not key:
        return False, "E2B API key is empty"
    
    if not key.startswith('e2b_'):
        return False, "E2B API key must start with 'e2b_'"
    
    if len(key) < 20:
        return False, "E2B API key seems too short"
    
    return True, "Valid E2B API key"


def validate_cors_origins(origins: str) -> Tuple[bool, str]:
    """Validate CORS origins"""
    if not origins:
        return False, "CORS origins are empty"
    
    origin_list = [o.strip() for o in origins.split(',')]
    
    for origin in origin_list:
        if not origin.startswith(('http://', 'https://')):
            return False, f"Invalid CORS origin: {origin}"
    
    return True, f"Valid CORS origins ({len(origin_list)} origins)"


def check_required_variables() -> Dict[str, Tuple[bool, str]]:
    """Check all required environment variables"""
    results = {}
    
    # Critical variables
    print_header("Checking Critical Variables")
    
    # MongoDB
    mongodb_uri = os.getenv('MONGODB_URI', '')
    results['MONGODB_URI'] = validate_mongodb_uri(mongodb_uri)
    
    # Redis
    redis_url = os.getenv('REDIS_URL', '')
    results['REDIS_URL'] = validate_redis_url(redis_url)
    
    # Groq API Keys
    groq_keys = os.getenv('GROQ_API_KEYS', '')
    results['GROQ_API_KEYS'] = validate_api_keys(groq_keys, 'Groq', 'gsk_')
    
    # Cerebras API Keys
    cerebras_keys = os.getenv('CEREBRAS_API_KEYS', '')
    results['CEREBRAS_API_KEYS'] = validate_api_keys(cerebras_keys, 'Cerebras', 'csk_')
    
    # E2B API Key
    e2b_key = os.getenv('E2B_API_KEY', '')
    results['E2B_API_KEY'] = validate_e2b_key(e2b_key)
    
    # JWT Secret
    jwt_secret = os.getenv('JWT_SECRET_KEY', '')
    results['JWT_SECRET_KEY'] = validate_jwt_secret(jwt_secret)
    
    # Celery (should match Redis URL)
    celery_broker = os.getenv('CELERY_BROKER_URL', '')
    results['CELERY_BROKER_URL'] = validate_redis_url(celery_broker)
    
    return results


def check_optional_variables() -> Dict[str, Tuple[bool, str]]:
    """Check optional environment variables"""
    results = {}
    
    print_header("Checking Optional Variables")
    
    # Bytez API Keys
    bytez_keys = os.getenv('BYTEZ_API_KEYS', '')
    if bytez_keys:
        results['BYTEZ_API_KEYS'] = (True, f"Bytez keys configured ({len(bytez_keys.split(','))} keys)")
    else:
        results['BYTEZ_API_KEYS'] = (True, "Bytez keys not configured (optional)")
    
    # GitHub OAuth
    github_client_id = os.getenv('GITHUB_CLIENT_ID', '')
    github_client_secret = os.getenv('GITHUB_CLIENT_SECRET', '')
    if github_client_id and github_client_secret:
        results['GITHUB_OAUTH'] = (True, "GitHub OAuth configured")
    else:
        results['GITHUB_OAUTH'] = (True, "GitHub OAuth not configured (optional)")
    
    return results


def check_production_settings() -> Dict[str, Tuple[bool, str]]:
    """Check production-specific settings"""
    results = {}
    
    print_header("Checking Production Settings")
    
    # Environment
    environment = os.getenv('ENVIRONMENT', 'development')
    if environment == 'production':
        results['ENVIRONMENT'] = (True, "Environment set to production")
    else:
        results['ENVIRONMENT'] = (False, f"Environment is '{environment}', should be 'production'")
    
    # Debug
    debug = os.getenv('DEBUG', 'true').lower()
    if debug == 'false':
        results['DEBUG'] = (True, "Debug mode disabled")
    else:
        results['DEBUG'] = (False, "Debug mode is enabled, should be 'false' in production")
    
    # CORS Origins
    cors_origins = os.getenv('CORS_ORIGINS', '')
    results['CORS_ORIGINS'] = validate_cors_origins(cors_origins)
    
    # Show Error Details
    show_errors = os.getenv('SHOW_ERROR_DETAILS', 'true').lower()
    if show_errors == 'false':
        results['SHOW_ERROR_DETAILS'] = (True, "Error details hidden")
    else:
        results['SHOW_ERROR_DETAILS'] = (False, "Error details are shown, should be 'false' in production")
    
    return results


def print_results(results: Dict[str, Tuple[bool, str]], category: str):
    """Print validation results"""
    for var_name, (is_valid, message) in results.items():
        if is_valid:
            print_success(f"{var_name}: {message}")
        else:
            print_error(f"{var_name}: {message}")


def generate_summary(all_results: Dict[str, Dict[str, Tuple[bool, str]]]) -> Tuple[int, int, int]:
    """Generate summary statistics"""
    total = 0
    passed = 0
    failed = 0
    
    for category_results in all_results.values():
        for is_valid, _ in category_results.values():
            total += 1
            if is_valid:
                passed += 1
            else:
                failed += 1
    
    return total, passed, failed


def main():
    """Main validation function"""
    print_header("Qbit Environment Variables Validator")
    print_info("This script validates environment variables for Render deployment")
    print_info("Make sure you have loaded your .env file or set environment variables\n")
    
    # Check if .env file exists
    if os.path.exists('.env'):
        print_success("Found .env file")
        print_info("Loading environment variables from .env file...")
        
        # Load .env file
        try:
            from dotenv import load_dotenv
            load_dotenv()
            print_success("Environment variables loaded\n")
        except ImportError:
            print_warning("python-dotenv not installed, using system environment variables\n")
    else:
        print_warning("No .env file found, using system environment variables\n")
    
    # Run validations
    all_results = {
        'required': check_required_variables(),
        'optional': check_optional_variables(),
        'production': check_production_settings()
    }
    
    # Print results
    print_results(all_results['required'], "Required")
    print_results(all_results['optional'], "Optional")
    print_results(all_results['production'], "Production")
    
    # Generate summary
    total, passed, failed = generate_summary(all_results)
    
    print_header("Validation Summary")
    print(f"Total checks: {total}")
    print_success(f"Passed: {passed}")
    if failed > 0:
        print_error(f"Failed: {failed}")
    else:
        print_success(f"Failed: {failed}")
    
    # Final verdict
    print()
    if failed == 0:
        print_success("✓ All validations passed! Ready for Render deployment.")
        print_info("\nNext steps:")
        print_info("1. Push your code to GitHub")
        print_info("2. Create a new Web Service on Render")
        print_info("3. Set environment variables in Render Dashboard")
        print_info("4. Deploy!")
        return 0
    else:
        print_error("✗ Some validations failed. Please fix the issues above.")
        print_info("\nRefer to DEPLOYMENT_GUIDE.md for detailed setup instructions.")
        return 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nValidation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {str(e)}")
        sys.exit(1)
