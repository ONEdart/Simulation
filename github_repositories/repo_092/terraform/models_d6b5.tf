# main.tf
resource "random_pet" "name" {
  length = 2
}

output "name" {
  value = random_pet.name.id
}
