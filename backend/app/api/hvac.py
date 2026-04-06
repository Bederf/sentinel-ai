def calculate_equipment_health(equipment: dict) -> dict:
    """Calculate health score for equipment based on health config.
    
    Uses real data when available; infers runtime from age if needed.
    Emits None values (not synthetic strings) for truly missing data.
    """
    health_config = load_json(HEALTH_CONFIG_PATH)
    eq_type = equipment.get("type", "").lower()

    # Use existing health score if no config
    if eq_type not in health_config:
        return {
            "health_score": equipment.get("health_score", 85),
            "status": get_health_status(equipment.get("health_score", 85)),
            "factors": {},
            "formula_version": FORMULA_VERSION_STATIC,
        }

    config = health_config[eq_type]
    weights = config.get("weights", {})
    thresholds = config.get("thresholds", {})

    # Calculate individual factors
    factors = {}

    # Age factor
    install_date = equipment.get("install_date")
    if install_date:
        try:
            install = datetime.fromisoformat(install_date.replace("Z", "+00:00"))
            age_years = (datetime.now() - install.replace(tzinfo=None)).days / 365
            expected_life = config.get("expected_life_years", 20)
            age_score = max(0, 100 - (age_years / expected_life) * 100)
            if age_years >= thresholds.get("age_critical_years", 18):
                age_score = max(0, age_score - 30)
            elif age_years >= thresholds.get("age_warning_years", 15):
                age_score = max(0, age_score - 15)
            factors["age"] = {"score": age_score, "value": f"{age_years:.1f} years"}
        except (ValueError, TypeError):
            # No valid install date: emit None, not 'Unknown'
            factors["age"] = {"score": 80, "value": None}
    else:
        # Missing install_date: emit None signal to frontend
        factors["age"] = {"score": 80, "value": None}

    # Service compliance factor
    last_service = equipment.get("last_service")
    service_interval = config.get("service_interval_days", 90)
    if last_service:
        try:
            service_date = datetime.fromisoformat(last_service.replace("Z", "+00:00"))
            days_since = (datetime.now() - service_date.replace(tzinfo=None)).days
            days_overdue = max(0, days_since - service_interval)
            service_score = max(0, 100 - days_overdue * 2)
            if days_overdue >= thresholds.get("service_overdue_days_critical", 90):
                service_score = max(0, service_score - 30)
            elif days_overdue >= thresholds.get("service_overdue_days_warning", 30):
                service_score = max(0, service_score - 15)
            factors["service"] = {"score": service_score, "value": f"{days_since} days ago"}
        except (ValueError, TypeError):
            # No valid service date: emit None
            factors["service"] = {"score": 70, "value": None}
    else:
        # Missing last_service: emit None signal (not 'Never')
        factors["service"] = {"score": 70, "value": None}

    # Runtime hours factor (simulated based on age if not available)
    runtime_hours = equipment.get("runtime_hours")
    if runtime_hours is None and install_date:
        try:
            install = datetime.fromisoformat(install_date.replace("Z", "+00:00"))
            age_days = (datetime.now() - install.replace(tzinfo=None)).days
            runtime_hours = age_days * 10  # Estimate 10 hours/day average
        except (ValueError, TypeError):
            runtime_hours = 10000
    elif runtime_hours is None:
        runtime_hours = 10000

    runtime_critical = thresholds.get("runtime_hours_critical", 40000)
    runtime_warning = thresholds.get("runtime_hours_warning", 20000)
    if runtime_hours >= runtime_critical:
        runtime_score = 40
    elif runtime_hours >= runtime_warning:
        runtime_score = 70
    else:
        runtime_score = 100 - (runtime_hours / runtime_warning) * 30
    factors["runtime"] = {"score": runtime_score, "value": f"{runtime_hours:,} hours"}

    # Fault history factor (use existing status as proxy)
    status = equipment.get("status", "normal")
    if status == "normal":
        fault_score = 100
    elif status == "warning":
        fault_score = 60
    else:
        fault_score = 30
    factors["fault_history"] = {"score": fault_score, "value": status}

    # Calculate weighted total
    total_score = (
        factors["age"]["score"] * weights.get("age_factor", 0.2)
        + factors["service"]["score"] * weights.get("service_compliance", 0.3)
        + factors["runtime"]["score"] * weights.get("runtime_hours", 0.2)
        + factors["fault_history"]["score"] * weights.get("fault_history", 0.3)
    )

    return {
        "health_score": round(total_score, 1),
        "status": get_health_status(total_score),
        "factors": factors,
        "formula_version": FORMULA_VERSION_STATIC,
    }
