// Run with mongosh after selecting the intended development database.
// Example inside mongosh: use jobless_simulator
// Then: load('docs/DB/001_initial_collections.js') from the repository root.
// Requires permission to list/create collections and create indexes.
// No credentials, document inserts, drops or existing-schema modifications.

(() => {
  if (['admin', 'config', 'local', 'test'].includes(db.getName())) {
    throw new Error('Select the application development database before loading this script.');
  }

  const names = ['resume_documents', 'job_documents'];
  const existing = db.getCollectionNames();
  if (names.some(name => existing.includes(name))) {
    throw new Error('An application collection already exists. Review it before applying changes.');
  }

  // Normalize SQL UUIDs to lowercase strings before writing documents.
  const uuid = {
    bsonType: 'string',
    pattern: '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
  };
  const text = { bsonType: 'string', pattern: '\\S' };
  const objectArray = { bsonType: 'array', items: { bsonType: 'object' } };

  db.createCollection('resume_documents', {
    validationLevel: 'strict',
    validationAction: 'error',
    validator: {
      $jsonSchema: {
        bsonType: 'object',
        additionalProperties: false,
        required: ['user_id', 'file_name', 'raw_text', 'extracted_data', 'uploaded_at'],
        properties: {
          _id: { bsonType: 'objectId' },
          user_id: uuid,
          file_name: text,
          raw_text: text,
          uploaded_at: { bsonType: 'date' },
          extracted_data: {
            bsonType: 'object',
            required: ['skills', 'education', 'experience', 'projects'],
            properties: {
              skills: { bsonType: 'array', items: text },
              education: objectArray,
              experience: objectArray,
              projects: objectArray,
            },
          },
        },
      },
    },
  });
  db.resume_documents.createIndex({ user_id: 1 }, { unique: true, name: 'resume_user_unique' });

  db.createCollection('job_documents', {
    validationLevel: 'strict',
    validationAction: 'error',
    validator: {
      $jsonSchema: {
        bsonType: 'object',
        additionalProperties: false,
        required: ['job_id', 'raw_jd', 'extracted_data', 'extracted_at'],
        properties: {
          _id: { bsonType: 'objectId' },
          job_id: uuid,
          raw_jd: text,
          extracted_at: { bsonType: 'date' },
          extracted_data: {
            bsonType: 'object',
            required: ['role_category', 'requirements', 'responsibilities'],
            properties: {
              role_category: text,
              responsibilities: { bsonType: 'array', items: text },
              requirements: {
                bsonType: 'array',
                items: {
                  bsonType: 'object',
                  required: ['skill_id', 'requirement_type', 'minimum_years', 'evidence'],
                  properties: {
                    skill_id: { bsonType: 'int', minimum: 1 },
                    requirement_type: { enum: ['REQUIRED', 'PREFERRED'] },
                    minimum_years: {
                      bsonType: ['int', 'long', 'double', 'decimal', 'null'],
                      minimum: 0,
                    },
                    evidence: text,
                  },
                },
              },
            },
          },
        },
      },
    },
  });
  db.job_documents.createIndex({ job_id: 1 }, { unique: true, name: 'job_document_job_unique' });
  db.job_documents.createIndex({ 'extracted_data.role_category': 1 }, { name: 'job_role_category' });

  print('Created resume_documents and job_documents with validators and indexes.');
})();
