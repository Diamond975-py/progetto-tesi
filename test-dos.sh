for i in {1..200}; do
curl -X POST  http://localhost:4566/restapis/cdc55094/prod/_user_request_/upload
done

