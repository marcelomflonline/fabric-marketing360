"""Publica os itens do repositório (pasta /fabric, criada pela integração Git do Fabric) num workspace.

    python cicd/deploy.py --ambiente PRD
"""
import argparse
import os

from azure.identity import ClientSecretCredential
from fabric_cicd import FabricWorkspace, publish_all_items, unpublish_all_orphan_items

ITENS = ["Notebook", "DataPipeline", "Lakehouse", "Warehouse", "SemanticModel", "Report", "Environment"]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ambiente", required=True, choices=["DEV", "PRD"])
    args = ap.parse_args()

    credencial = ClientSecretCredential(os.environ["AZURE_TENANT_ID"], os.environ["AZURE_CLIENT_ID"],
                                        os.environ["AZURE_CLIENT_SECRET"])
    ws = FabricWorkspace(
        workspace_id=os.environ["FABRIC_WORKSPACE_ID"],
        environment=args.ambiente,                 # chave usada em parameter.yml
        repository_directory="fabric",
        item_type_in_scope=ITENS,
        token_credential=credencial,
    )
    publish_all_items(ws)
    unpublish_all_orphan_items(ws)   # remove do destino o que foi apagado no repositório
