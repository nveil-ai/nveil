# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

import asyncio
import os
import platform
import sys
from pathlib import Path

from database.core.database import db
from database.services.license_catalog_service import LicenseCatalogService
from logger import ERROR, INFO, logger
from pandas_ods_reader import read_ods
from sqlalchemy import text
from sqlalchemy.schema import CreateSchema
from utils import get_secret

def print_license_table(config: dict):
    """Affiche un tableau stylisé des licences et leurs features."""
    header = f"║ {'LICENSE':<25} ║ {'FEATURE':<35} ║ {'VALUE':<15} ║"
    separator = "╠" + "═" * 27 + "╬" + "═" * 37 + "╬" + "═" * 17 + "╣"
    top = "╔" + "═" * 27 + "╦" + "═" * 37 + "╦" + "═" * 17 + "╗"
    bottom = "╚" + "═" * 27 + "╩" + "═" * 37 + "╩" + "═" * 17 + "╝"

    print(f"\n{top}")
    print(header)
    print(separator)

    for license_name, features in config.items():
        for feature_name, details in features.items():
            # On gère le cas où details est une valeur brute ou un dict avec 'value'
            value = details['value'] if isinstance(details, dict) and 'value' in details else details
            print(f"║ {str(license_name):<25} ║ {str(feature_name):<35} ║ {str(value):<15} ║")

    print(f"{bottom}\n")

DB_SCHEMA = get_secret("DATABASE_SCHEMA")
DATABASE_URL = get_secret("DATABASE_URL")

async def update_license_catalog():
    dir_path = os.path.dirname(os.path.realpath(__file__))
    license_path = Path(dir_path + "/license/Nveil_AI_Licenses_Catalog.ods")
    df = read_ods(license_path)
    df_transformed = df.melt(
        id_vars=['feature'],
        var_name='license',
        value_name='value'
    )
    df_transformed = df_transformed[['license', 'feature', 'value']]

    config_dict = {}

    for license_name, group in df_transformed.groupby('license'):
        config_dict[license_name] = {}
        for _, row in group.iterrows():
            feature_name = row['feature']
            feature_value = row['value']
            infos = {
                'value': feature_value,
                'in_db': False
            }
            config_dict[license_name][feature_name] = infos

    try:
        db.initialize(url=DATABASE_URL, echo=False)
        from server_service.database.models.base import Base

        async with db.engine.begin() as conn:
            await conn.execute(CreateSchema(DB_SCHEMA, if_not_exists=True))
            await conn.run_sync(Base.metadata.create_all)
        logger().logp(INFO, "✅ Database tables initialized")
    except Exception as e:
        logger().logp(ERROR, f"❌ Database initialization failed: {e}")
        return

    # Create session manually instead of using Depends
    async with db.session() as session:
        license_catalog_service = LicenseCatalogService(session)
        license_catalog = await license_catalog_service.license_catalog_repo.get_many(limit=1000)
        actual_config_dict = {}
        for lic in license_catalog:
            if lic.license not in actual_config_dict:
                actual_config_dict[lic.license] = {}
            actual_config_dict[lic.license][lic.feature] = {
                'value': lic.value,
                'id': lic.id
            }

        print("\nNew License Catalog")
        print_license_table(config_dict)
        print("Actual License Catalog")
        print_license_table(actual_config_dict)
        
        logger().logp(INFO, "Do you want to update the catalog above? (yes/no)")
        line = sys.stdin.readline().rstrip()
        if line.lower() != 'yes':
            return

        # Handle deletions and updates for existing records
        for lic in license_catalog:
            # 1. License no longer exists in config
            if lic.license not in config_dict:
                await license_catalog_service.license_catalog_repo.delete_by_id(lic.id)
                logger().logp(INFO, f"✅ 🗑️ Deleted license {lic.license} feature {lic.feature}")
                continue

            # 2. Feature no longer exists for this license
            if lic.feature not in config_dict[lic.license]:
                await license_catalog_service.license_catalog_repo.delete_by_id(lic.id)
                logger().logp(INFO, f"✅ 🗑️ Deleted license {lic.license} feature {lic.feature}")
                continue

            # 3. Feature exists, check for update
            new_val = str(config_dict[lic.license][lic.feature]['value'])
            if new_val != lic.value:
                await license_catalog_service.license_catalog_repo.update_by_id(lic.id, value=new_val)
                logger().logp(INFO, f"✅ 📀 Updated license {lic.license} feature {lic.feature} to {new_val}")
            else:
                logger().logp(INFO, f"✅ 📅 License {lic.license} feature {lic.feature} is up to date")
            
            # Mark as processed in config_dict
            config_dict[lic.license][lic.feature]['in_db'] = True

        # Handle additions for new records
        for license_name, features in config_dict.items():
            for feature_name, feature_info in features.items():
                if not feature_info.get('in_db', False):
                    await license_catalog_service.license_catalog_repo.create(
                        license=license_name,
                        feature=feature_name,
                        value=str(feature_info['value'])
                    )
                    logger().logp(INFO, f"✅ 📚 Added license {license_name} feature {feature_name} with value {feature_info['value']}")
    await db.close()

if __name__ == "__main__":
    asyncio.run(update_license_catalog())

