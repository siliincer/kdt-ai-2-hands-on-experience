from ..core.load_environment_var import settings  # 환경변수 로드

APP_ENV = str(settings.APP_ENV).strip().lower()

if APP_ENV in ["local", "dev", "development"]:
    is_dev = True
elif APP_ENV in ["prod", "production"]:
    is_dev = False
else:
    raise ValueError(f"""Invalid APP_ENV value: {APP_ENV}.
        Must be one of ['local', 'dev', 'development',
        'prod', 'production'].""")
