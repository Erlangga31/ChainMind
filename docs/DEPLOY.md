# Panduan deployment AWS (scaffold)

**Belum siap untuk deployment produksi.** Infrastruktur di bawah ini belum pernah dideploy atau diuji terhadap akun AWS nyata. Jangan jalankan `make deploy` atau `make destroy` tanpa review biaya dan persetujuan pemilik akun.

## Prasyarat

- Python 3.12, Node.js 22, AWS CDK v2, Docker hanya bila proses bundling Lambda membutuhkannya.
- Akun dan region AWS dengan izin membuat VPC/NAT Gateway, API Gateway, Cognito, Lambda, DynamoDB, S3, KMS, CloudTrail, Bedrock, Step Functions, EventBridge, CloudWatch, dan Secrets Manager.
- Bedrock model access telah diaktifkan di region yang sama; atur context `bedrockModelId`.
- SAP BTP Integration Suite tenant, destination, OAuth client, dan SAP Cloud Connector atau private connectivity yang disetujui organisasi.

## Langkah yang belum dijalankan

1. Tinjau template dan biaya VPC dua AZ dengan satu NAT Gateway, interface endpoints, Bedrock, CloudTrail, serta log retention.
2. Bootstrap environment sekali: `cdk bootstrap aws://ACCOUNT/REGION`.
3. Siapkan role viewer/approver di Cognito User Pool. CDK menyediakan User Pool, groups, hosted domain, dan OAuth authorization-code client, tetapi dashboard OAuth/PKCE redirect dan token exchange belum diimplementasikan.
4. Isi secret Event Mesh dan signing link melalui Secrets Manager. Jangan taruh credential nyata di `.env`, CDK context, atau repository.
5. Atur callback URL Cognito ke origin dashboard HTTPS yang telah disetujui. Hubungkan dashboard ke issuer/client ID sebelum mengaktifkan authorizer pada deployment.
6. Konfigurasikan endpoint/credential SAP Integration Suite, SAP Cloud Connector/private link, Teams/Slack webhook atau SES verified sender.
7. Tinjau CloudTrail, KMS key policy, Lambda package dependencies, alarms, API throttling, dan retensi sebelum deployment.

## Validasi yang tersedia

`make synth` hanya memvalidasi sintesis template CDK. Pytest memeriksa sejumlah resource dan properties. Tidak ada tahap deploy, panggilan AWS runtime, provisioning SAP, atau verifikasi end-to-end AWS dalam workspace ini. Lambda source masih perlu paket dependency runtime yang lengkap sebelum deploy.

## Perintah berisiko

- `make deploy` membuat atau mengubah resource berbayar dan membutuhkan kredensial AWS.
- `make destroy` menghapus stack; resource dengan retain policy tetap tersimpan dan mungkin tetap menimbulkan biaya.

Keduanya sengaja tidak dijalankan dalam proses pengembangan ini.
