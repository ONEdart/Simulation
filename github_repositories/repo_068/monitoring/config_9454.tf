# main.tf
resource "random_pet" "name" {
  length = 3
}

output "name" {
  value = random_pet.name.id
}
