#!/usr/bin/env bash
set -e

# Change directory to Terraform configs
cd "$(dirname "$0")"

# Export credentials from Jenkins environment (already injected)
export ARM_CLIENT_ID="${AZURE_CLIENT_ID}"
export ARM_CLIENT_SECRET="${AZURE_CLIENT_SECRET}"
export ARM_TENANT_ID="${AZURE_TENANT_ID}"
export ARM_SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID_VAR}"

export TF_VAR_client_id="${ARM_CLIENT_ID}"
export TF_VAR_client_secret="${ARM_CLIENT_SECRET}"
export TF_VAR_tenant_id="${ARM_TENANT_ID}"
export TF_VAR_subscription_id="${ARM_SUBSCRIPTION_ID}"

# Initialize Terraform backend
terraform init -backend-config="resource_group_name=MyPatientSurveyRG" \
               -backend-config="storage_account_name=mypatientsurveytfstate" \
               -backend-config="container_name=tfstate" \
               -backend-config="key=patient_survey.tfstate"

# Import existing resources into state if they exist
declare -A resources=(
    ["azurerm_mssql_server.sql_server"]="Microsoft.Sql/servers/patientsurveysql"
    ["azurerm_network_security_group.monitoring_nsg"]="Microsoft.Network/networkSecurityGroups/monitoring-nsg"
    ["azurerm_storage_account.monitoring"]="Microsoft.Storage/storageAccounts/mypatientsurveymonitor"
)

for res in "${!resources[@]}"; do
    if ! terraform state list | grep -q "$res"; then
        echo "Importing $res..."
        terraform import "$res" "/subscriptions/${ARM_SUBSCRIPTION_ID}/resourceGroups/MyPatientSurveyRG/providers/${resources[$res]}" \
        || echo "$res not found, will be created by Terraform"
    else
        echo "$res already in state, skipping import"
    fi
done

echo "✅ Prework complete: Terraform state now includes existing resources"
